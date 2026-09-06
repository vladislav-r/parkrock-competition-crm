import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AgeGroup, Ascent, CompetitionSet, Event, EventStage, FinalCategoryResult, FinalCategoryRoute,
    FinalRoute, FinalRouteAttempt, Participant, QualificationCategorySnapshot, QualificationResultSnapshot, Route,
)
from app.schemas import (
    CompletedRouteRead, PublicFinalAttemptRead, PublicFinalResultRead, PublicFinalResultsResponse,
    PublicFinalRouteRead, PublicParticipantRead, PublicResultRead, PublicResultsResponse, PublicSetRead,
)
from app.services import age_on, medal_for_points

router = APIRouter(prefix="/public", tags=["public"])


def set_participant_counts(db: Session, items: list[CompetitionSet]) -> dict[uuid.UUID, tuple[int, int]]:
    if not items:
        return {}
    rows = db.execute(select(
        Participant.set_id, func.count(), func.count().filter(Participant.checked_in_at.is_not(None)),
    ).where(Participant.set_id.in_([item.id for item in items]), Participant.archived_at.is_(None))
        .group_by(Participant.set_id))
    return {set_id: (count, checked_in) for set_id, count, checked_in in rows}


def set_read(db: Session, item: CompetitionSet, counts: dict[uuid.UUID, tuple[int, int]] | None = None) -> PublicSetRead:
    if counts is None:
        counts = set_participant_counts(db, [item])
    count, checked_in_count = counts.get(item.id, (0, 0))
    return PublicSetRead(id=item.id, name=item.name, scheduled_on=item.scheduled_on,
        time_label=item.time_label, capacity=item.capacity,
        participant_count=count, checked_in_count=checked_in_count, status=item.status,
        confirmed_at=item.confirmed_at)


def live_result_rows(db: Session, event: Event) -> list[dict]:
    participants = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None))).all())
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True))).all()}
    groups = list(db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all())
    completed_by_participant: dict[uuid.UUID, list[uuid.UUID]] = {}
    for participant_id, route_id in db.execute(select(Ascent.participant_id, Ascent.route_id).join(Participant, Participant.id == Ascent.participant_id).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None),
        Ascent.is_completed.is_(True))).all():
        if route_id in routes:
            completed_by_participant.setdefault(participant_id, []).append(route_id)

    rows = []
    for participant in participants:
        route_ids = completed_by_participant.get(participant.id, [])
        participant_age = age_on(participant.birth_year or participant.birth_date.year, event.starts_on)
        group = next((item for item in groups if item.sex == participant.sex
            and item.min_age <= participant_age and (item.max_age is None or participant_age <= item.max_age)), None)
        points = sum(routes[route_id].points for route_id in route_ids) if route_ids else None
        medal = medal_for_points(group, points)
        rows.append({
            "participant": participant,
            "group_name": group.name if group else "Вне возрастной группы",
            "completed_route_ids": route_ids,
            "completed_count": len(route_ids) if route_ids else None,
            "points": points,
            "has_result": bool(route_ids),
            "place": None,
            "is_finalist": False,
            "is_finisher": medal is not None,
            "medal": medal,
        })

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if row["has_result"]:
            grouped.setdefault(row["group_name"], []).append(row)
    for group_rows in grouped.values():
        group_rows.sort(key=lambda row: (-row["points"], row["participant"].start_number))
        group = next((item for item in groups if item.name == group_rows[0]["group_name"]), None)
        quota = group.finalist_count if group else 10
        finalist_score = group_rows[min(quota, len(group_rows)) - 1]["points"] if quota > 0 else None
        previous_score = None
        previous_place = 0
        for index, row in enumerate(group_rows, start=1):
            row["place"] = previous_place if row["points"] == previous_score else index
            row["is_finalist"] = quota > 0 and finalist_score is not None and row["points"] >= finalist_score
            previous_score = row["points"]
            previous_place = row["place"]
    return rows


@router.get("/results", response_model=PublicResultsResponse)
def results(group: str | None = None, set_id: uuid.UUID | None = None,
            db: Session = Depends(get_db)) -> PublicResultsResponse:
    event = db.scalar(select(Event).where(Event.is_public.is_(True)).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Нет опубликованного фестиваля")
    rows = live_result_rows(db, event)
    if group:
        rows = [row for row in rows if row["group_name"] == group]
    if set_id:
        rows = [row for row in rows if row["participant"].set_id == set_id]
    rows.sort(key=lambda row: (
        row["group_name"], not row["has_result"],
        -(row["points"] or 0), row["participant"].surname, row["participant"].name,
    ))
    all_groups = list(db.scalars(select(AgeGroup.name).where(
        AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all())
    updated_at = db.scalar(select(func.max(Ascent.updated_at)).join(
        Participant, Participant.id == Ascent.participant_id).where(
        Participant.event_id == event.id, Ascent.is_completed.is_(True)))
    sets = db.scalars(select(CompetitionSet).where(
        CompetitionSet.event_id == event.id).order_by(
            CompetitionSet.scheduled_on.asc().nulls_last(),
            CompetitionSet.time_label,
            CompetitionSet.name,
            CompetitionSet.id,
        )).all()
    final_groups: list[str] = []
    if event.stage in (EventStage.final, EventStage.completed):
        snapshot_group_ids = set(db.scalars(select(QualificationCategorySnapshot.age_group_id).where(
            QualificationCategorySnapshot.event_id == event.id)).all())
        final_groups = [group.name for group in db.scalars(select(AgeGroup).where(
            AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all()
            if group.id in snapshot_group_ids and group.finalist_count > 0 and group.participates_in_final]
    counts = set_participant_counts(db, sets)
    return PublicResultsResponse(
        event_id=event.id, event_title=event.title, location=event.location,
        starts_on=event.starts_on, stage=event.stage, details_enabled=event.public_result_details_enabled,
        updated_at=updated_at, groups=all_groups, final_groups=final_groups,
        sets=[set_read(db, item, counts) for item in sets],
        results=[PublicResultRead(
            participant_id=row["participant"].id, place=row["place"],
            start_number=row["participant"].start_number,
            full_name=f"{row['participant'].surname} {row['participant'].name}",
            club=row["participant"].club, completed_count=row["completed_count"],
            points=row["points"], has_result=row["has_result"],
            is_finalist=row["is_finalist"], group_name=row["group_name"],
            is_finisher=row["is_finisher"], medal=row["medal"],
            set_id=row["participant"].set_id,
        ) for row in rows],
    )


@router.get("/final-results", response_model=PublicFinalResultsResponse)
def final_results(group: str, db: Session = Depends(get_db)) -> PublicFinalResultsResponse:
    event = db.scalar(select(Event).where(Event.is_public.is_(True)).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Нет опубликованного фестиваля")
    if event.stage in (EventStage.preparation, EventStage.qualification):
        raise HTTPException(status_code=409, detail="Финал еще не начался")
    age_group = db.scalar(select(AgeGroup).where(AgeGroup.event_id == event.id, AgeGroup.name == group))
    if not age_group or age_group.finalist_count <= 0 or not age_group.participates_in_final:
        raise HTTPException(status_code=404, detail="Возрастная категория не участвует в финале")
    assignments = list(db.scalars(select(FinalCategoryRoute).where(
        FinalCategoryRoute.event_id == event.id, FinalCategoryRoute.age_group_id == age_group.id)).all())
    route_ids = [item.final_route_id for item in assignments]
    routes = list(db.scalars(select(FinalRoute).where(
        FinalRoute.id.in_(route_ids)).order_by(FinalRoute.number)).all()) if route_ids else []
    route_by_id = {route.id: route for route in routes}
    snapshot = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id, QualificationCategorySnapshot.age_group_id == age_group.id))
    if not snapshot:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    results = list(db.scalars(select(FinalCategoryResult).where(
        FinalCategoryResult.category_snapshot_id == snapshot.id)).all())
    qualification = {item.id: item for item in db.scalars(select(QualificationResultSnapshot).where(
        QualificationResultSnapshot.category_snapshot_id == snapshot.id)).all()}
    attempts = list(db.scalars(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id.in_([item.id for item in results]))).all()) if results else []
    attempts_by_result = {(item.final_category_result_id, item.final_route_id): item for item in attempts}
    results_with_attempts = {item.final_category_result_id for item in attempts}
    rows = [PublicFinalResultRead(
        participant_id=result.participant_id, place=result.place, start_number=qualification[result.qualification_result_snapshot_id].start_number,
        full_name=" ".join(filter(None, (qualification[result.qualification_result_snapshot_id].surname, qualification[result.qualification_result_snapshot_id].name))),
        club=qualification[result.qualification_result_snapshot_id].club, qualification_place=qualification[result.qualification_result_snapshot_id].place,
        exit_order=qualification[result.qualification_result_snapshot_id].exit_order,
        has_result=result.id in results_with_attempts,
        score=result.score_tenths / 10, top_count=result.top_count, zone_count=result.zone_count,
        attempts=[PublicFinalAttemptRead(route_number=route.number,
            zone_attempt=(attempts_by_result.get((result.id, route.id)).zone_attempt if attempts_by_result.get((result.id, route.id)) else None),
            top_attempt=(attempts_by_result.get((result.id, route.id)).top_attempt if attempts_by_result.get((result.id, route.id)) else None)) for route in routes],
    ) for result in results]
    rows.sort(key=lambda item: (
        not item.has_result,
        item.place if item.has_result and item.place is not None else 10_000,
        item.exit_order if item.exit_order is not None else 10_000,
    ))
    updated_at = max((item.updated_at for item in attempts), default=None)
    return PublicFinalResultsResponse(category_name=age_group.name,
        routes=[PublicFinalRouteRead(number=route.number, name=route.name) for route in routes], results=rows, updated_at=updated_at)


@router.get("/participants/{participant_id}", response_model=PublicParticipantRead)
def participant_detail(participant_id: uuid.UUID, db: Session = Depends(get_db)) -> PublicParticipantRead:
    participant = db.get(Participant, participant_id)
    if not participant or participant.archived_at is not None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    event = db.get(Event, participant.event_id)
    if not event.public_result_details_enabled:
        raise HTTPException(status_code=403, detail="Подробные результаты участников пока закрыты")
    row = next(item for item in live_result_rows(db, event) if item["participant"].id == participant.id)
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True))).all()}
    completed = [routes[route_id] for route_id in row["completed_route_ids"] if route_id in routes]
    completed.sort(key=lambda route: (-route.points, route.number))
    return PublicParticipantRead(
        participant_id=participant.id, place=row["place"], is_finalist=row["is_finalist"],
        is_finisher=row["is_finisher"], medal=row["medal"],
        start_number=participant.start_number, full_name=f"{participant.surname} {participant.name}",
        club=participant.club, group_name=row["group_name"], completed_count=row["completed_count"],
        points=row["points"], has_result=row["has_result"],
        completed_routes=[CompletedRouteRead(number=route.number, name=route.name,
            grade=route.grade, points=route.points) for route in completed],
    )
