import json
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, select, or_
from sqlalchemy.orm import Session

from app.models import AgeGroup, Ascent, Event, Participant, PublishedResult, Route, FinalCategoryResult, QualificationCategorySnapshot


def final_group_participates(group: AgeGroup) -> bool:
    return group.finalist_count > 0 and group.participates_in_final


def inactive_final_result_ids(event_id):
    return select(FinalCategoryResult.id).join(QualificationCategorySnapshot,
        QualificationCategorySnapshot.id == FinalCategoryResult.category_snapshot_id).join(
        AgeGroup, AgeGroup.id == QualificationCategorySnapshot.age_group_id).where(
        FinalCategoryResult.event_id == event_id,
        or_(AgeGroup.participates_in_final.is_(False), AgeGroup.finalist_count <= 0))


def age_on(birth_date_or_year: date | int, on_date: date) -> int:
    birth_year = birth_date_or_year if isinstance(birth_date_or_year, int) else birth_date_or_year.year
    return on_date.year - birth_year


def participant_age_error(birth_date_or_year: date | int, on_date: date) -> str | None:
    age = age_on(birth_date_or_year, on_date)
    if age < 0:
        return "возраст не может быть отрицательным"
    if age > 99:
        return "возраст не может быть больше 99 лет"
    return None


def participant_group(db: Session, event: Event, participant: Participant, groups: list[AgeGroup] | None = None) -> str:
    group = participant_age_group(db, event, participant, groups)
    return group.name if group else "Вне возрастной группы"


def participant_age_group(db: Session, event: Event, participant: Participant, groups: list[AgeGroup] | None = None) -> AgeGroup | None:
    age = age_on(participant.birth_year or participant.birth_date.year, event.starts_on)
    if groups is not None:
        return next((item for item in groups if item.sex == participant.sex and item.min_age <= age
                     and (item.max_age is None or age <= item.max_age)), None)
    return db.scalar(select(AgeGroup).where(
        AgeGroup.event_id == event.id, AgeGroup.sex == participant.sex,
        AgeGroup.min_age <= age, (AgeGroup.max_age.is_(None) | (AgeGroup.max_age >= age)),
    ).order_by(AgeGroup.sort_order))


def medal_for_points(group: AgeGroup | None, points: int | None) -> str | None:
    if not group or points is None:
        return None
    for medal in ("gold", "silver", "bronze"):
        minimum = getattr(group, f"{medal}_min_points")
        maximum = getattr(group, f"{medal}_max_points")
        if minimum is not None and points >= minimum and (maximum is None or points <= maximum):
            return medal
    return None


def publish_set(db: Session, set_id) -> None:
    participants = db.scalars(select(Participant).where(Participant.set_id == set_id, Participant.archived_at.is_(None))).all()
    if not participants:
        return
    event = db.get(Event, participants[0].event_id)
    db.execute(delete(PublishedResult).where(PublishedResult.set_id == set_id))
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True))).all()}
    for participant in participants:
        completed = db.scalars(select(Ascent).where(Ascent.participant_id == participant.id, Ascent.is_completed.is_(True))).all()
        route_ids = [ascent.route_id for ascent in completed if ascent.route_id in routes]
        group = participant_age_group(db, event, participant)
        points = sum(routes[route_id].points for route_id in route_ids)
        medal = medal_for_points(group, points)
        db.add(PublishedResult(event_id=event.id, set_id=set_id, participant_id=participant.id,
            group_name=group.name if group else "Вне возрастной группы", completed_count=len(route_ids),
            points=points, is_finisher=medal is not None, medal=medal,
            completed_route_ids=",".join(str(route_id) for route_id in route_ids),
            completed_routes_json=json.dumps([{"number": routes[route_id].number, "name": routes[route_id].name,
                "grade": routes[route_id].grade, "points": routes[route_id].points} for route_id in route_ids], ensure_ascii=False),
            published_at=datetime.now(timezone.utc)))
    db.flush()
    recalculate_places(db, event.id)


def recalculate_places(db: Session, event_id) -> None:
    results = db.scalars(select(PublishedResult).where(PublishedResult.event_id == event_id)
        .order_by(PublishedResult.group_name, PublishedResult.points.desc())).all()
    groups: dict[str, list[PublishedResult]] = {}
    for result in results:
        groups.setdefault(result.group_name, []).append(result)
    event = db.get(Event, event_id)
    participants = {item.id: item for item in db.scalars(select(Participant).where(Participant.event_id == event_id)).all()}
    age_groups = {item.name: item for item in db.scalars(select(AgeGroup).where(AgeGroup.event_id == event_id)).all()}
    for rows in groups.values():
        group = age_groups.get(rows[0].group_name) if rows else None
        quota = group.finalist_count if group and final_group_participates(group) else 0
        finalist_score = rows[min(quota, len(rows)) - 1].points if rows and quota > 0 else None
        previous_score = None
        previous_place = 0
        for index, row in enumerate(rows, start=1):
            score = row.points
            row.place = previous_place if score == previous_score else index
            row.is_finalist = quota > 0 and finalist_score is not None and row.points >= finalist_score
            participant = participants.get(row.participant_id)
            group = participant_age_group(db, event, participant) if participant else None
            row.medal = medal_for_points(group, row.points)
            row.is_finisher = row.medal is not None
            previous_score = score
            previous_place = row.place


def refresh_published_route_values(db: Session, event_id) -> None:
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event_id, Route.is_active.is_(True))).all()}
    published = db.scalars(select(PublishedResult).where(PublishedResult.event_id == event_id)).all()
    refreshed_at = datetime.now(timezone.utc)
    for result in published:
        completed_ids = [route_id for value in result.completed_route_ids.split(",") if value
                         and (route_id := uuid.UUID(value)) in routes]
        result.completed_count = len(completed_ids)
        result.points = sum(routes[route_id].points for route_id in completed_ids)
        result.completed_routes_json = json.dumps([
            {"number": routes[route_id].number, "name": routes[route_id].name,
             "grade": routes[route_id].grade, "points": routes[route_id].points}
            for route_id in completed_ids
        ], ensure_ascii=False)
        result.published_at = refreshed_at
    db.flush()
    recalculate_places(db, event_id)
