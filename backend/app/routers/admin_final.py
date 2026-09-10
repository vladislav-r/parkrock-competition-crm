import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import delete, func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import backup_service
from app.db import get_db
from app.deps import get_current_admin
from app.audit import write_audit
from app.models import (
    Admin, AgeGroup, Ascent, Event, EventStage, Participant, QualificationCategorySnapshot,
    FinalCategoryResult, FinalCategoryRoute, FinalRoute, FinalRouteAttempt, OperationRecord, JudgeResultConflict, UserRole,
    QualificationResultSnapshot, Route,
)
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.routers.public import live_result_rows
from app.schemas import (
    FinalAttemptInput, FinalCategoryParticipationUpdate, FinalCategoryResultsResponse, FinalCategoryRoutesUpdate,
    FinalCategorySetup, FinalParticipantResultRead, FinalResultUpdate, FinalRouteAttemptRead,
    FinalRouteRead, FinalSetupResponse, FinalStatusResponse, QualificationCategoryReview,
    QualificationCategoryStatus, QualificationResultReview, VersionedAction, JudgeConflictResolution,
)


router = APIRouter(
    prefix="/admin/final", tags=["admin-final"],
    dependencies=[Depends(require_permission(Permission.final_manage))],
)


def group_settings(group: AgeGroup) -> dict[str, object]:
    fields = (
        "name", "sex", "min_age", "max_age", "sort_order", "finalist_count",
        "bronze_min_points", "bronze_max_points", "silver_min_points", "silver_max_points",
        "gold_min_points", "gold_max_points",
    )
    return {field: getattr(group, field).value if field == "sex" else getattr(group, field) for field in fields}


def qualification_state(db: Session, event: Event) -> tuple[list[AgeGroup], dict[str, list[dict]], dict[uuid.UUID, str]]:
    groups = list(db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all())
    grouped_rows = {group.name: [] for group in groups}
    for row in live_result_rows(db, event):
        if row["has_result"] and row["group_name"] in grouped_rows:
            grouped_rows[row["group_name"]].append(row)
    for rows in grouped_rows.values():
        rows.sort(key=lambda row: (row["place"], row["participant"].start_number))
    signatures: dict[uuid.UUID, str] = {}
    for group in groups:
        result_values = [{
            "participant_id": str(row["participant"].id),
            "start_number": row["participant"].start_number,
            "surname": row["participant"].surname,
            "name": row["participant"].name,
            "points": row["points"],
            "completed_count": row["completed_count"],
            "place": row["place"],
            "is_finalist": row["is_finalist"],
            "completed_route_ids": sorted(str(route_id) for route_id in row["completed_route_ids"]),
        } for row in grouped_rows[group.name]]
        encoded = json.dumps(
            {"settings": group_settings(group), "results": result_values},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        signatures[group.id] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return groups, grouped_rows, signatures


def final_category_state(
    db: Session, event: Event, group_id: uuid.UUID,
) -> tuple[QualificationCategorySnapshot | None, str | None]:
    category = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id,
        QualificationCategorySnapshot.age_group_id == group_id,
    ))
    if not category:
        return None, None
    route_ids = list(db.scalars(
        select(FinalCategoryRoute.final_route_id)
        .join(FinalRoute, FinalRoute.id == FinalCategoryRoute.final_route_id)
        .where(
            FinalCategoryRoute.event_id == event.id,
            FinalCategoryRoute.age_group_id == group_id,
        )
        .order_by(FinalRoute.number)
    ).all())
    results = list(db.scalars(
        select(FinalCategoryResult)
        .where(FinalCategoryResult.category_snapshot_id == category.id)
        .order_by(FinalCategoryResult.participant_id)
    ).all())
    attempts = list(db.scalars(
        select(FinalRouteAttempt)
        .where(FinalRouteAttempt.final_category_result_id.in_([item.id for item in results]))
        .order_by(FinalRouteAttempt.final_category_result_id, FinalRouteAttempt.final_route_id)
    ).all()) if results else []
    encoded = json.dumps({
        "route_ids": [str(route_id) for route_id in route_ids],
        "results": [{
            "participant_id": str(result.participant_id),
            "attempts": [{
                "route_id": str(attempt.final_route_id),
                "zone_attempt": attempt.zone_attempt,
                "top_attempt": attempt.top_attempt,
            } for attempt in attempts if attempt.final_category_result_id == result.id],
        } for result in results],
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return category, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def status_response(db: Session, event: Event) -> FinalStatusResponse:
    groups, grouped_rows, signatures = qualification_state(db, event)
    final_result_counts = dict(db.execute(
        select(QualificationCategorySnapshot.age_group_id, func.count(func.distinct(FinalCategoryResult.id)))
        .join(FinalCategoryResult, FinalCategoryResult.category_snapshot_id == QualificationCategorySnapshot.id)
        .join(FinalRouteAttempt, FinalRouteAttempt.final_category_result_id == FinalCategoryResult.id)
        .where(
            QualificationCategorySnapshot.event_id == event.id,
            or_(FinalRouteAttempt.zone_attempt.is_not(None), FinalRouteAttempt.top_attempt.is_not(None)),
        )
        .group_by(QualificationCategorySnapshot.age_group_id)
    ).all())
    categories = []
    for group in groups:
        final_snapshot, final_signature = final_category_state(db, event, group.id)
        categories.append(QualificationCategoryStatus(
            id=group.id, name=group.name, result_count=len(grouped_rows[group.name]),
            final_result_count=final_result_counts.get(group.id, 0),
            finalist_count=sum(1 for row in grouped_rows[group.name] if row["is_finalist"]),
            participates_in_final=group.finalist_count > 0,
            confirmed=bool(group.qualification_confirmed_at and group.qualification_signature == signatures[group.id]),
            confirmed_at=group.qualification_confirmed_at,
            final_confirmed=bool(
                final_snapshot and final_snapshot.final_confirmed_at
                and final_snapshot.final_signature == final_signature
            ),
            final_confirmed_at=final_snapshot.final_confirmed_at if final_snapshot else None,
            expected_version=group.version,
        ))
    snapshot_results = db.scalar(select(func.count()).select_from(QualificationResultSnapshot).where(
        QualificationResultSnapshot.event_id == event.id)) or 0
    snapshot_finalists = db.scalar(select(func.count()).select_from(QualificationResultSnapshot).where(
        QualificationResultSnapshot.event_id == event.id, QualificationResultSnapshot.is_finalist.is_(True))) or 0
    return FinalStatusResponse(
        event_id=event.id, stage=event.stage, qualification_started_at=event.qualification_started_at,
        final_started_at=event.final_started_at,
        completed_at=event.completed_at, event_version=event.version, categories=categories,
        all_categories_confirmed=bool(categories) and all(item.confirmed for item in categories),
        all_final_categories_confirmed=bool(
            [item for item in categories if item.participates_in_final]
        ) and all(item.final_confirmed for item in categories if item.participates_in_final),
        snapshot_results=snapshot_results, snapshot_finalists=snapshot_finalists,
    )


def _test_database(db: Session) -> bool:
    return bool(db.bind and (make_url(str(db.bind.url)).database or "").endswith("_test"))


def create_stage_checkpoint(db: Session, event: Event, target_stage: str, note: str) -> dict[str, object]:
    if _test_database(db):
        return {"filename": f"test-{target_stage}.dump", "note": note}
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    try:
        return backup_service.create_backup(
            db, source="stage-transition", note=note,
            context={"event_id": str(event.id), "target_stage": target_stage, "kind": "stage-transition"},
        )
    except backup_service.BackupError as error:
        raise HTTPException(status_code=503, detail=f"Переход отменён: резервная копия не создана. {error}") from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()


def restore_stage_checkpoint(
    db: Session, event: Event, admin: Admin, target_stage: str, record: OperationRecord,
) -> FinalStatusResponse:
    locked = False
    safety = None
    target_labels = {"preparation": "Подготовка", "qualification": "Квалификация", "final": "Финал"}
    target_label = target_labels[target_stage]
    try:
        if not _test_database(db):
            locked = backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False)
            if not locked:
                raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
            safety = backup_service.create_backup(
                db, source="pre-rollback", note=f"ДО ОТКАТА НАЗАД К ЭТАПУ «{target_label}»",
                context={"event_id": str(event.id), "target_stage": target_stage, "kind": "pre-rollback"},
            )
        if target_stage == "preparation":
            participant_ids = select(Participant.id).where(Participant.event_id == event.id)
            db.execute(delete(Ascent).where(Ascent.participant_id.in_(participant_ids)))
            groups = list(db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id).with_for_update()).all())
            for group in groups:
                group.qualification_confirmed_at = None
                group.qualification_confirmed_by_id = None
                group.qualification_signature = None
            event.stage = EventStage.preparation
            event.qualification_started_at = None
            event.final_started_at = None
            event.completed_at = None
        elif target_stage == "qualification":
            db.execute(delete(FinalRouteAttempt).where(FinalRouteAttempt.event_id == event.id))
            db.execute(delete(FinalCategoryResult).where(FinalCategoryResult.event_id == event.id))
            db.execute(delete(QualificationResultSnapshot).where(QualificationResultSnapshot.event_id == event.id))
            db.execute(delete(QualificationCategorySnapshot).where(QualificationCategorySnapshot.event_id == event.id))
            event.stage = EventStage.qualification
            event.final_started_at = None
            event.completed_at = None
        else:
            event.stage = EventStage.final
            event.completed_at = None
        db.flush()
        write_audit(
            db, actor=admin, action="event.stage.rollback", target_type="event",
            target_id=str(event.id), new_value={
                "stage": target_stage,
                "pre_rollback_backup": safety["filename"] if safety else None,
                "preserved": ["routes", "categories", "sets", "users", "judge_assignments"],
            },
        )
        response = status_response(db, event)
        complete_operation(record, response.model_dump(mode="json"))
        db.commit()
        return response
    except backup_service.BackupError as error:
        raise HTTPException(status_code=503, detail=f"Откат не выполнен: {error}") from error
    finally:
        if locked:
            backup_service.BACKUP_OPERATION_LOCK.release()


def final_group_participates(group: AgeGroup) -> bool:
    return group.finalist_count > 0


def final_group_short_name(group: AgeGroup) -> str:
    if group.min_age >= 19:
        return "М" if group.sex.value == "male" else "Ж"
    prefix = "М" if group.sex.value == "male" else "Д"
    return f"{prefix}{group.min_age}-{group.max_age}"


def ensure_final_routes(db: Session, event: Event) -> list[FinalRoute]:
    routes = list(db.scalars(select(FinalRoute).where(FinalRoute.event_id == event.id).order_by(FinalRoute.number)).all())
    if not routes:
        db.add_all([FinalRoute(event_id=event.id, number=number, name=f"Финал {number}") for number in range(1, 9)])
        db.flush()
        routes = list(db.scalars(select(FinalRoute).where(FinalRoute.event_id == event.id).order_by(FinalRoute.number)).all())
    if len(routes) != 8:
        raise HTTPException(status_code=409, detail="Для финала должны быть настроены восемь трасс")
    return routes


def final_setup_response(db: Session, event: Event) -> FinalSetupResponse:
    if event.stage in (EventStage.preparation, EventStage.qualification):
        raise HTTPException(status_code=409, detail="Настройка финальных трасс доступна после запуска финала")
    routes = ensure_final_routes(db, event)
    groups = list(db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id, AgeGroup.finalist_count > 0,
    ).order_by(AgeGroup.sort_order)).all())
    assignments = list(db.scalars(select(FinalCategoryRoute).where(FinalCategoryRoute.event_id == event.id)).all())
    route_ids_by_group: dict[uuid.UUID, list[uuid.UUID]] = {group.id: [] for group in groups}
    group_names_by_route: dict[uuid.UUID, list[str]] = {route.id: [] for route in routes}
    names = {group.id: group.name for group in groups}
    for assignment in assignments:
        route_ids_by_group.setdefault(assignment.age_group_id, []).append(assignment.final_route_id)
        group_names_by_route.setdefault(assignment.final_route_id, []).append(names.get(assignment.age_group_id, ""))
    return FinalSetupResponse(
        event_version=event.version,
        routes=[FinalRouteRead(id=route.id, number=route.number, name=route.name,
                               assigned_categories=sorted(filter(None, group_names_by_route[route.id]))) for route in routes],
        categories=[FinalCategorySetup(
            id=group.id, name=group.name, short_name=final_group_short_name(group),
            participates=final_group_participates(group),
            finalist_count=db.scalar(select(func.count()).select_from(FinalCategoryResult).join(
                QualificationCategorySnapshot, FinalCategoryResult.category_snapshot_id == QualificationCategorySnapshot.id
            ).where(QualificationCategorySnapshot.event_id == event.id, QualificationCategorySnapshot.age_group_id == group.id)) or 0,
            route_ids=sorted(route_ids_by_group[group.id], key=lambda route_id: next(route.number for route in routes if route.id == route_id)),
        ) for group in groups],
    )


def route_score_tenths(zone_attempt: int | None, top_attempt: int | None) -> int:
    if top_attempt is not None:
        return 251 - top_attempt
    if zone_attempt is not None:
        return 101 - zone_attempt
    return 0


def recalculate_final_category(db: Session, category_snapshot_id: uuid.UUID, route_ids: list[uuid.UUID]) -> None:
    db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.id == category_snapshot_id).with_for_update())
    results = list(db.scalars(select(FinalCategoryResult).where(
        FinalCategoryResult.category_snapshot_id == category_snapshot_id)).all())
    qualification_places = dict(db.execute(select(
        QualificationResultSnapshot.id, QualificationResultSnapshot.place,
    ).where(QualificationResultSnapshot.id.in_([
        item.qualification_result_snapshot_id for item in results
    ]))).all()) if results else {}
    attempts = list(db.scalars(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id.in_([item.id for item in results]))).all()) if results else []
    attempts_by_result = {(item.final_category_result_id, item.final_route_id): item for item in attempts}
    rows: list[tuple[FinalCategoryResult, tuple[int, int, int, int, int, int], bool]] = []
    for result in results:
        route_attempts = [attempts_by_result.get((result.id, route_id)) for route_id in route_ids]
        score = sum(route_score_tenths(item.zone_attempt, item.top_attempt) for item in route_attempts if item)
        tops = sum(1 for item in route_attempts if item and item.top_attempt is not None)
        zones = sum(1 for item in route_attempts if item and (item.zone_attempt is not None or item.top_attempt is not None))
        top_attempts = sum(item.top_attempt for item in route_attempts if item and item.top_attempt is not None)
        zone_attempts = sum(
            item.zone_attempt if item.zone_attempt is not None else item.top_attempt or 0
            for item in route_attempts
            if item and (item.zone_attempt is not None or item.top_attempt is not None)
        )
        has_result = any(item is not None for item in route_attempts)
        final_values = (score, tops, zones, top_attempts, zone_attempts)
        if (result.score_tenths, result.top_count, result.zone_count, result.top_attempts, result.zone_attempts) != final_values:
            result.score_tenths, result.top_count, result.zone_count, result.top_attempts, result.zone_attempts = final_values
        qualification_place = qualification_places.get(result.qualification_result_snapshot_id, 10_000)
        rows.append((result, (*final_values, qualification_place), has_result))
    for result, _, has_result in rows:
        if not has_result:
            result.place = None
    ranked_rows = [item for item in rows if item[2]]
    ranked_rows.sort(key=lambda item: (-item[1][0], -item[1][1], -item[1][2], item[1][3], item[1][4], item[1][5]))
    previous_key: tuple[int, int, int, int, int, int] | None = None
    place = 0
    for index, (result, key, _) in enumerate(ranked_rows, start=1):
        if key != previous_key:
            place = index
            previous_key = key
        result.place = place


def final_category_results_response(db: Session, event: Event, group: AgeGroup) -> FinalCategoryResultsResponse:
    setup = final_setup_response(db, event)
    category = next((item for item in setup.categories if item.id == group.id), None)
    if not category or not category.participates:
        raise HTTPException(status_code=409, detail="Возрастная категория не участвует в финале")
    if len(category.route_ids) != 4:
        raise HTTPException(status_code=409, detail="Сначала назначьте категории четыре финальные трассы")
    category_snapshot = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id, QualificationCategorySnapshot.age_group_id == group.id))
    if not category_snapshot:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    routes = [route for route in setup.routes if route.id in category.route_ids]
    route_by_id = {route.id: route for route in routes}
    results = list(db.scalars(select(FinalCategoryResult).where(
        FinalCategoryResult.category_snapshot_id == category_snapshot.id)).all())
    qualification = {item.id: item for item in db.scalars(select(QualificationResultSnapshot).where(
        QualificationResultSnapshot.category_snapshot_id == category_snapshot.id)).all()}
    attempts = list(db.scalars(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id.in_([item.id for item in results]))).all()) if results else []
    attempts_by_result = {(item.final_category_result_id, item.final_route_id): item for item in attempts}
    results_with_attempts = {item.final_category_result_id for item in attempts}
    result_rows = []
    for result in results:
        qualification_row = qualification[result.qualification_result_snapshot_id]
        route_attempts = []
        for route_id in category.route_ids:
            attempt = attempts_by_result.get((result.id, route_id))
            route = route_by_id[route_id]
            route_attempts.append(FinalRouteAttemptRead(
                route_id=route_id, route_number=route.number, route_name=route.name,
                zone_attempt=attempt.zone_attempt if attempt else None, top_attempt=attempt.top_attempt if attempt else None,
                score=route_score_tenths(attempt.zone_attempt, attempt.top_attempt) / 10 if attempt else 0,
            ))
        result_rows.append(FinalParticipantResultRead(
            id=result.id, participant_id=result.participant_id, start_number=qualification_row.start_number,
            full_name=" ".join(filter(None, (qualification_row.surname, qualification_row.name, qualification_row.patronymic))),
            club=qualification_row.club, qualification_place=qualification_row.place, exit_order=qualification_row.exit_order,
            score=result.score_tenths / 10, top_count=result.top_count, zone_count=result.zone_count,
            top_attempts=result.top_attempts, zone_attempts=result.zone_attempts, place=result.place,
            has_result=result.id in results_with_attempts,
            version=result.version, attempts=route_attempts,
        ))
    result_rows.sort(key=lambda item: (
        not item.has_result,
        item.place if item.has_result and item.place is not None else 10_000,
        item.exit_order if item.exit_order is not None else 10_000,
    ))
    return FinalCategoryResultsResponse(category_id=group.id, category_name=group.name, routes=routes, results=result_rows)


@router.get("", response_model=FinalStatusResponse)
def read_final_status(db: Session = Depends(get_db)) -> FinalStatusResponse:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return status_response(db, event)


@router.get("/setup", response_model=FinalSetupResponse)
def read_final_setup(db: Session = Depends(get_db)) -> FinalSetupResponse:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return final_setup_response(db, event)


@router.put("/categories/{group_id}/routes", response_model=FinalSetupResponse)
def update_category_final_routes(
    group_id: uuid.UUID, payload: FinalCategoryRoutesUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalSetupResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    group = db.get(AgeGroup, group_id)
    if not event or not group or group.event_id != event.id:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Настройка финальных трасс доступна только во время финала")
    if not final_group_participates(group):
        raise HTTPException(status_code=409, detail="Возрастная категория не участвует в финале")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.category-routes.update",
        target_type="age_group", target_id=str(group.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_event_version)
    routes = ensure_final_routes(db, event)
    known_route_ids = {route.id for route in routes}
    if set(payload.route_ids) - known_route_ids:
        raise HTTPException(status_code=422, detail="Выбрана неизвестная финальная трасса")
    category_snapshot = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id, QualificationCategorySnapshot.age_group_id == group.id))
    has_attempts = category_snapshot and db.scalar(select(func.count()).select_from(FinalRouteAttempt).join(
        FinalCategoryResult, FinalRouteAttempt.final_category_result_id == FinalCategoryResult.id
    ).where(FinalCategoryResult.category_snapshot_id == category_snapshot.id))
    if has_attempts:
        raise HTTPException(status_code=409, detail="Нельзя менять трассы категории после внесения финальных результатов")
    db.execute(delete(FinalCategoryRoute).where(
        FinalCategoryRoute.event_id == event.id, FinalCategoryRoute.age_group_id == group.id))
    db.add_all([FinalCategoryRoute(event_id=event.id, age_group_id=group.id, final_route_id=route_id) for route_id in payload.route_ids])
    event.version += 1
    db.flush()
    response = final_setup_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.put("/categories/{group_id}/participation", response_model=FinalSetupResponse)
def update_category_final_participation(
    group_id: uuid.UUID, payload: FinalCategoryParticipationUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalSetupResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    group = db.get(AgeGroup, group_id)
    if not event or not group or group.event_id != event.id:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Состав категорий финала можно менять только во время финала")
    raise HTTPException(status_code=409, detail="Участие категории в финале определяется количеством финалистов в настройках")


@router.get("/categories/{group_id}/final-results", response_model=FinalCategoryResultsResponse)
def read_final_category_results(group_id: uuid.UUID, db: Session = Depends(get_db)) -> FinalCategoryResultsResponse:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    return final_category_results_response(db, event, group)


@router.get("/judge-conflicts")
def read_judge_conflicts(db: Session = Depends(get_db)) -> list[dict]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        return []
    conflicts = db.scalars(select(JudgeResultConflict).where(
        JudgeResultConflict.event_id == event.id, JudgeResultConflict.resolution.is_(None),
    ).order_by(JudgeResultConflict.created_at)).all()
    rows = []
    for conflict in conflicts:
        result = db.get(FinalCategoryResult, conflict.final_result_id) if conflict.final_result_id else None
        attempt = db.scalar(select(FinalRouteAttempt).where(
            FinalRouteAttempt.final_category_result_id == conflict.final_result_id,
            FinalRouteAttempt.final_route_id == conflict.final_route_id,
        )) if result else None
        rows.append({
            **json.loads(conflict.details_json), "id": str(conflict.id),
            "created_at": conflict.created_at.isoformat(),
            "expected_version": result.version if result else 1,
            "can_apply_judge": bool(result and attempt and event.stage == EventStage.final),
            "current": {"zone_attempt": attempt.zone_attempt, "top_attempt": attempt.top_attempt} if attempt else None,
        })
    return rows


@router.post("/judge-conflicts/{conflict_id}/resolve")
def resolve_judge_conflict(
    conflict_id: uuid.UUID, payload: JudgeConflictResolution, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> dict:
    if admin.role not in {UserRole.administrator, UserRole.chief_judge, UserRole.secretary}:
        raise HTTPException(status_code=403, detail="Выбор результата доступен только старшим сотрудникам")
    conflict = db.get(JudgeResultConflict, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="Конфликт не найден")
    event = db.scalar(select(Event).where(Event.id == conflict.event_id).with_for_update(read=True))
    # Match the category -> result lock order used by judge and secretary writes.
    result = db.get(FinalCategoryResult, conflict.final_result_id) if conflict.final_result_id else None
    if result:
        category = db.scalar(select(QualificationCategorySnapshot).where(
            QualificationCategorySnapshot.id == result.category_snapshot_id).with_for_update())
        result = db.scalar(select(FinalCategoryResult).where(FinalCategoryResult.id == result.id)
                           .with_for_update().execution_options(populate_existing=True))
    conflict = db.scalar(select(JudgeResultConflict).where(JudgeResultConflict.id == conflict_id)
                         .with_for_update().execution_options(populate_existing=True))
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="judge.conflict.resolve",
        target_type="judge_conflict", target_id=str(conflict_id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if conflict.resolution:
        raise HTTPException(status_code=409, detail="Другой сотрудник уже разрешил конфликт")
    if result:
        require_version(result, payload.expected_version)
    attempt = db.scalar(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id == conflict.final_result_id,
        FinalRouteAttempt.final_route_id == conflict.final_route_id,
    )) if result else None
    before = {"zone_attempt": attempt.zone_attempt, "top_attempt": attempt.top_attempt} if attempt else None
    if payload.choice == "judge":
        if not result or not attempt or event.stage != EventStage.final:
            raise HTTPException(status_code=409, detail="Этот результат больше нельзя применить к текущему финалу")
        submitted = json.loads(conflict.details_json)["submitted"]
        attempt.zone_attempt = submitted["zone_attempt"]
        attempt.top_attempt = submitted["top_attempt"]
        result.version += 1
        category.final_confirmed_at = None
        category.final_confirmed_by_id = None
        category.final_signature = None
        db.flush()
        route_ids = list(db.scalars(select(FinalCategoryRoute.final_route_id).where(
            FinalCategoryRoute.age_group_id == category.age_group_id,
        )).all())
        recalculate_final_category(db, category.id, route_ids)
    conflict.resolution = payload.choice
    conflict.resolved_by_id = admin.id
    conflict.resolved_at = datetime.now(timezone.utc)
    response = {"id": str(conflict_id), "resolution": payload.choice, "previous": before,
                "submitted": json.loads(conflict.details_json)["submitted"]}
    complete_operation(record, response)
    db.commit()
    return response


@router.put("/categories/{group_id}/participants/{participant_id}/final-results", response_model=FinalCategoryResultsResponse)
def update_final_result(
    group_id: uuid.UUID, participant_id: uuid.UUID, payload: FinalResultUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalCategoryResultsResponse | dict:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Финальные результаты можно изменять только во время финала")
    category_snapshot = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id, QualificationCategorySnapshot.age_group_id == group.id)
        .with_for_update().execution_options(populate_existing=True))
    if not category_snapshot:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    final_result = db.scalar(select(FinalCategoryResult).where(
        FinalCategoryResult.category_snapshot_id == category_snapshot.id, FinalCategoryResult.participant_id == participant_id).with_for_update())
    if not final_result:
        raise HTTPException(status_code=404, detail="Участник не является финалистом этой категории")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.result.update",
        target_type="participant", target_id=str(participant_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(final_result, payload.expected_version)
    setup = final_setup_response(db, event)
    category = next((item for item in setup.categories if item.id == group.id), None)
    if not category or len(category.route_ids) != 4:
        raise HTTPException(status_code=409, detail="Сначала назначьте категории четыре финальные трассы")
    if {item.route_id for item in payload.attempts} != set(category.route_ids):
        raise HTTPException(status_code=422, detail="Результаты должны соответствовать назначенным четырем трассам")
    db.execute(delete(FinalRouteAttempt).where(FinalRouteAttempt.final_category_result_id == final_result.id))
    db.add_all([FinalRouteAttempt(
        event_id=event.id, final_category_result_id=final_result.id, final_route_id=item.route_id,
        zone_attempt=item.zone_attempt, top_attempt=item.top_attempt,
    ) for item in payload.attempts])
    final_result.version += 1
    db.flush()
    recalculate_final_category(db, category_snapshot.id, category.route_ids)
    db.flush()
    response = final_category_results_response(db, event, group).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/categories/{group_id}/final-confirm", response_model=FinalStatusResponse)
def confirm_final_category(
    group_id: uuid.UUID, payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    group = db.get(AgeGroup, group_id)
    if not event or not group or group.event_id != event.id:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Результаты финала можно подтверждать только во время финала")
    if not final_group_participates(group):
        raise HTTPException(status_code=409, detail="Возрастная категория не участвует в финале")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.category-confirm",
        target_type="age_group", target_id=str(group.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    setup = final_setup_response(db, event)
    category_setup = next((item for item in setup.categories if item.id == group.id), None)
    if not category_setup or len(category_setup.route_ids) != 4:
        raise HTTPException(status_code=409, detail="Сначала назначьте категории четыре финальные трассы")
    category, signature = final_category_state(db, event, group.id)
    if not category or not signature:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    category.final_confirmed_at = datetime.now(timezone.utc)
    category.final_confirmed_by_id = admin.id
    category.final_signature = signature
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="final.category-confirm", target_type="age_group",
        target_id=str(group.id), new_value={"name": group.name},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/categories/{group_id}/final-reopen", response_model=FinalStatusResponse)
def reopen_final_category(
    group_id: uuid.UUID, payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    group = db.get(AgeGroup, group_id)
    if not event or not group or group.event_id != event.id:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Подтверждение финала уже зафиксировано")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.category-reopen",
        target_type="age_group", target_id=str(group.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    category, _ = final_category_state(db, event, group.id)
    if not category:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    category.final_confirmed_at = None
    category.final_confirmed_by_id = None
    category.final_signature = None
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="final.category-reopen", target_type="age_group",
        target_id=str(group.id), new_value={"name": group.name},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/final-results/confirm-all", response_model=FinalStatusResponse)
def confirm_all_final_categories(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Результаты финала сейчас недоступны")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.confirm-all",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    setup = final_setup_response(db, event)
    incomplete = [item.name for item in setup.categories if len(item.route_ids) != 4]
    if incomplete:
        raise HTTPException(
            status_code=409,
            detail=f"Сначала назначьте четыре трассы категориям: {', '.join(incomplete)}",
        )
    confirmed_at = datetime.now(timezone.utc)
    confirmed_names = []
    for group in db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id, AgeGroup.finalist_count > 0,
    ).order_by(AgeGroup.sort_order)).all():
        category, signature = final_category_state(db, event, group.id)
        if not category or not signature:
            raise HTTPException(status_code=409, detail=f"Не удалось подготовить результаты группы «{group.name}»")
        category.final_confirmed_at = confirmed_at
        category.final_confirmed_by_id = admin.id
        category.final_signature = signature
        confirmed_names.append(group.name)
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="final.confirm-all", target_type="event", target_id=str(event.id),
        new_value={"categories": confirmed_names},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/final-results/reopen-all", response_model=FinalStatusResponse)
def reopen_all_final_categories(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Подтверждение финала уже зафиксировано")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.reopen-all",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    snapshots = list(db.scalars(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id,
    ).with_for_update()).all())
    for category in snapshots:
        category.final_confirmed_at = None
        category.final_confirmed_by_id = None
        category.final_signature = None
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="final.reopen-all", target_type="event", target_id=str(event.id),
        new_value={"categories": len(snapshots)},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.get("/categories/{group_id}/results", response_model=QualificationCategoryReview)
def read_category_results(group_id: uuid.UUID, db: Session = Depends(get_db)) -> QualificationCategoryReview:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    if event.stage in (EventStage.preparation, EventStage.qualification):
        _, grouped_rows, signatures = qualification_state(db, event)
        rows = grouped_rows[group.name]
        confirmed = bool(group.qualification_confirmed_at and group.qualification_signature == signatures[group.id])
        results = [QualificationResultReview(
            participant_id=row["participant"].id, start_number=row["participant"].start_number,
            full_name=" ".join(filter(None, (row["participant"].surname, row["participant"].name, row["participant"].patronymic))),
            club=row["participant"].club, completed_count=row["completed_count"], points=row["points"],
            place=row["place"], is_finalist=row["is_finalist"], exit_order=None,
        ) for row in rows]
    else:
        category = db.scalar(select(QualificationCategorySnapshot).where(
            QualificationCategorySnapshot.event_id == event.id,
            QualificationCategorySnapshot.age_group_id == group.id,
        ))
        snapshot_rows = [] if not category else list(db.scalars(select(QualificationResultSnapshot).where(
            QualificationResultSnapshot.category_snapshot_id == category.id,
        ).order_by(QualificationResultSnapshot.place, QualificationResultSnapshot.start_number)).all())
        confirmed = True
        results = [QualificationResultReview(
            participant_id=row.participant_id, start_number=row.start_number,
            full_name=" ".join(filter(None, (row.surname, row.name, row.patronymic))), club=row.club,
            completed_count=row.completed_count, points=row.points, place=row.place, is_finalist=row.is_finalist,
            exit_order=row.exit_order,
        ) for row in snapshot_rows]
    return QualificationCategoryReview(
        category_id=group.id, category_name=group.name, confirmed=confirmed, results=results,
    )


@router.get("/categories/{group_id}/snapshot.csv")
def export_category_snapshot_csv(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_permission(Permission.exports_create)),
) -> Response:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    if event.stage in (EventStage.preparation, EventStage.qualification):
        raise HTTPException(status_code=409, detail="Снимок квалификации будет доступен после запуска финала")
    review = read_category_results(group_id, db)
    content = io.StringIO(newline="")
    writer = csv.writer(content, delimiter=";", lineterminator="\r\n")
    writer.writerow((f"Возрастная группа: {group.name}",))
    writer.writerow(())
    writer.writerow(("Место", "Порядок выхода", "Стартовый номер", "Участник", "Клуб", "Пройдено трасс", "Очки", "Статус"))
    for item in review.results:
        writer.writerow((
            item.place, item.exit_order or "", item.start_number, item.full_name, item.club,
            item.completed_count, item.points, "Финалист" if item.is_finalist else "",
        ))
    write_audit(
        db, actor=admin, action="export.qualification-snapshot", target_type="age_group",
        target_id=str(group.id), new_value={"name": group.name, "format": "csv", "rows": len(review.results)},
    )
    db.commit()
    filename = quote(f"снимок-квалификации-{group.name}.csv")
    return Response(
        content="\ufeff" + content.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/categories/{group_id}/confirm", response_model=FinalStatusResponse)
def confirm_category(
    group_id: uuid.UUID, payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    if event.stage != EventStage.qualification:
        raise HTTPException(status_code=409, detail="Квалификация уже завершена")
    if not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Сначала начните квалификацию")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.category-confirm",
        target_type="age_group", target_id=str(group.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(group, payload.expected_version)
    _, _, signatures = qualification_state(db, event)
    group.qualification_confirmed_at = datetime.now(timezone.utc)
    group.qualification_confirmed_by_id = admin.id
    group.qualification_signature = signatures[group.id]
    db.flush()
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/categories/{group_id}/reopen", response_model=FinalStatusResponse)
def reopen_category(
    group_id: uuid.UUID, payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    group = db.get(AgeGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    event = db.get(Event, group.event_id)
    if event.stage != EventStage.qualification:
        raise HTTPException(status_code=409, detail="Квалификация уже завершена")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.category-reopen",
        target_type="age_group", target_id=str(group.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(group, payload.expected_version)
    group.qualification_confirmed_at = None
    group.qualification_confirmed_by_id = None
    group.qualification_signature = None
    db.flush()
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/qualification/start", response_model=FinalStatusResponse)
def start_qualification(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.start",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.preparation or event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Квалификация уже началась")
    require_version(event, payload.expected_version)
    checkpoint = create_stage_checkpoint(db, event, "qualification", "До начала этапа «Квалификация»")
    event.stage = EventStage.qualification
    event.qualification_started_at = datetime.now(timezone.utc)
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="qualification.start", target_type="event", target_id=str(event.id),
        new_value={"backup": checkpoint["filename"]},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/qualification/cancel", response_model=FinalStatusResponse)
def cancel_qualification(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.cancel",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.qualification or not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Отменить можно только запущенную квалификацию")
    require_version(event, payload.expected_version)
    return restore_stage_checkpoint(db, event, admin, "preparation", record)


@router.post("/qualification/confirm-all", response_model=FinalStatusResponse)
def confirm_all_categories(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.qualification or not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Квалификация сейчас недоступна")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.confirm-all",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    groups, _, signatures = qualification_state(db, event)
    confirmed_at = datetime.now(timezone.utc)
    for group in groups:
        group.qualification_confirmed_at = confirmed_at
        group.qualification_confirmed_by_id = admin.id
        group.qualification_signature = signatures[group.id]
    db.flush()
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/qualification/reopen-all", response_model=FinalStatusResponse)
def reopen_all_categories(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.qualification:
        raise HTTPException(status_code=409, detail="Подтверждение квалификации уже зафиксировано переходом в финал")
    if not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Квалификация ещё не начата")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="qualification.reopen-all",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    groups = list(db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id).with_for_update()).all())
    for group in groups:
        group.qualification_confirmed_at = None
        group.qualification_confirmed_by_id = None
        group.qualification_signature = None
    event.version += 1
    db.flush()
    write_audit(
        db, actor=admin, action="qualification.reopen-all", target_type="event", target_id=str(event.id),
        new_value={"categories": [group.name for group in groups]},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/start", response_model=FinalStatusResponse)
def start_final(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.start",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.qualification:
        raise HTTPException(status_code=409, detail="Финал уже запущен")
    if not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Сначала начните квалификацию")
    require_version(event, payload.expected_version)
    groups, grouped_rows, signatures = qualification_state(db, event)
    unconfirmed = [group.name for group in groups if not group.qualification_confirmed_at
                   or group.qualification_signature != signatures[group.id]]
    if unconfirmed:
        raise HTTPException(status_code=409, detail=f"Подтвердите результаты категорий: {', '.join(unconfirmed)}")

    checkpoint = create_stage_checkpoint(db, event, "final", "До начала этапа «Финал»")

    db.execute(delete(QualificationResultSnapshot).where(QualificationResultSnapshot.event_id == event.id))
    db.execute(delete(QualificationCategorySnapshot).where(QualificationCategorySnapshot.event_id == event.id))
    ensure_final_routes(db, event)
    routes = {route.id: route for route in db.scalars(select(Route).where(
        Route.event_id == event.id).order_by(Route.sort_order)).all()}
    final_results: list[tuple[QualificationCategorySnapshot, QualificationResultSnapshot]] = []
    for group in groups:
        settings = group_settings(group)
        category = QualificationCategorySnapshot(
            event_id=event.id, age_group_id=group.id, name=group.name, sex=group.sex,
            min_age=group.min_age, max_age=group.max_age, sort_order=group.sort_order,
            finalist_count=group.finalist_count,
            settings_json=json.dumps(settings, ensure_ascii=False, sort_keys=True), signature=signatures[group.id],
        )
        db.add(category)
        db.flush()
        finalist_order = sorted(
            (row for row in grouped_rows[group.name] if row["is_finalist"]),
            key=lambda row: (-row["place"], row["participant"].surname.casefold(),
                             row["participant"].name.casefold(), row["participant"].start_number),
        )
        exit_orders = {row["participant"].id: index for index, row in enumerate(finalist_order, start=1)}
        for row in grouped_rows[group.name]:
            participant = row["participant"]
            completed_routes = [{
                "id": str(route_id), "number": routes[route_id].number, "name": routes[route_id].name,
                "grade": routes[route_id].grade, "points": routes[route_id].points,
            } for route_id in sorted(row["completed_route_ids"], key=lambda route_id: routes[route_id].sort_order)]
            result_snapshot = QualificationResultSnapshot(
                event_id=event.id, category_snapshot_id=category.id, participant_id=participant.id,
                start_number=participant.start_number, surname=participant.surname, name=participant.name,
                patronymic=participant.patronymic, club=participant.club,
                completed_count=row["completed_count"], points=row["points"], place=row["place"],
                is_finalist=row["is_finalist"], exit_order=exit_orders.get(participant.id),
                completed_routes_json=json.dumps(completed_routes, ensure_ascii=False),
            )
            db.add(result_snapshot)
            if row["is_finalist"]:
                final_results.append((category, result_snapshot))
    db.flush()
    db.add_all([FinalCategoryResult(
        event_id=event.id, category_snapshot_id=category.id,
        qualification_result_snapshot_id=result_snapshot.id, participant_id=result_snapshot.participant_id,
    ) for category, result_snapshot in final_results])
    event.stage = EventStage.final
    event.final_started_at = datetime.now(timezone.utc)
    event.completed_at = None
    db.flush()
    write_audit(
        db, actor=admin, action="final.start", target_type="event", target_id=str(event.id),
        new_value={"backup": checkpoint["filename"]},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/cancel", response_model=FinalStatusResponse)
def cancel_final(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="final.cancel",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Отменить можно только запущенный финал")
    require_version(event, payload.expected_version)
    return restore_stage_checkpoint(db, event, admin, "qualification", record)


@router.post("/complete", response_model=FinalStatusResponse)
def complete_event(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="event.complete",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Завершить можно только этап финала")
    require_version(event, payload.expected_version)
    if db.scalar(select(JudgeResultConflict.id).where(
        JudgeResultConflict.event_id == event.id, JudgeResultConflict.resolution.is_(None),
    ).limit(1)):
        raise HTTPException(status_code=409, detail="Сначала разрешите конфликты результатов судей")
    unconfirmed = []
    for group in db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id, AgeGroup.finalist_count > 0,
    ).order_by(AgeGroup.sort_order)).all():
        category, signature = final_category_state(db, event, group.id)
        if not category or not category.final_confirmed_at or category.final_signature != signature:
            unconfirmed.append(group.name)
    if unconfirmed:
        raise HTTPException(
            status_code=409,
            detail=f"Подтвердите результаты финала по группам: {', '.join(unconfirmed)}",
        )
    checkpoint = create_stage_checkpoint(db, event, "completed", "До завершения фестиваля")
    event.stage = EventStage.completed
    event.completed_at = datetime.now(timezone.utc)
    db.flush()
    write_audit(
        db, actor=admin, action="event.complete", target_type="event", target_id=str(event.id),
        new_value={"backup": checkpoint["filename"]},
    )
    response = status_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/reopen", response_model=FinalStatusResponse)
def reopen_completed_event(
    payload: VersionedAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> FinalStatusResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="event.reopen",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    if event.stage != EventStage.completed:
        raise HTTPException(status_code=409, detail="Отменить можно только завершённый фестиваль")
    require_version(event, payload.expected_version)
    return restore_stage_checkpoint(db, event, admin, "final", record)
