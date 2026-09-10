import uuid
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clubs import current_club_names
from app.db import get_db
from app.deps import get_current_admin
from app.audit import write_audit
from app.models import (
    Admin, Event, EventStage, FinalCategoryResult, FinalCategoryRoute, FinalRoute,
    FinalRouteAttempt, QualificationCategorySnapshot, QualificationResultSnapshot, JudgeResultConflict,
)
from app.operations import OperationId, begin_operation, complete_operation
from app.permissions import Permission, require_permission
from app.routers.admin_final import recalculate_final_category, route_score_tenths
from app.schemas import (
    JudgeFinalRouteRead, JudgeParticipantRead, JudgeResultCreate, JudgeWorkspaceResponse,
)


router = APIRouter(
    prefix="/judge", tags=["judge"],
    dependencies=[Depends(require_permission(Permission.judge_results))],
)


def ensure_final_active(event: Event) -> None:
    if event.stage != EventStage.final or event.final_started_at is None:
        raise HTTPException(status_code=409, detail="Рабочее место судьи откроется после запуска финала")


def assigned_final_route(db: Session, event: Event, admin: Admin) -> FinalRoute:
    route = db.get(FinalRoute, admin.assigned_final_route_id) if admin.assigned_final_route_id else None
    if not route or route.event_id != event.id:
        raise HTTPException(status_code=409, detail="Для учетной записи не назначена финальная трасса")
    return route


def workspace_response(db: Session, event: Event, route: FinalRoute) -> JudgeWorkspaceResponse:
    club_names = current_club_names(db, event.id)
    assignments = list(db.scalars(select(FinalCategoryRoute).where(
        FinalCategoryRoute.event_id == event.id,
        FinalCategoryRoute.final_route_id == route.id,
    )).all())
    group_ids = {item.age_group_id for item in assignments}
    category_snapshots = list(db.scalars(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id,
        QualificationCategorySnapshot.age_group_id.in_(group_ids),
    )).all()) if group_ids else []
    category_by_id = {item.id: item for item in category_snapshots}
    results = list(db.scalars(select(FinalCategoryResult).where(
        FinalCategoryResult.event_id == event.id,
        FinalCategoryResult.category_snapshot_id.in_(category_by_id),
    )).all()) if category_by_id else []
    qualification_by_id = {item.id: item for item in db.scalars(select(QualificationResultSnapshot).where(
        QualificationResultSnapshot.id.in_([result.qualification_result_snapshot_id for result in results]),
    )).all()} if results else {}
    attempts = {item.final_category_result_id: item for item in db.scalars(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id.in_([result.id for result in results]),
        FinalRouteAttempt.final_route_id == route.id,
    )).all()} if results else {}
    participants = []
    for result in results:
        category = category_by_id[result.category_snapshot_id]
        qualification = qualification_by_id[result.qualification_result_snapshot_id]
        attempt = attempts.get(result.id)
        participants.append(JudgeParticipantRead(
            final_result_id=result.id,
            participant_id=result.participant_id,
            category_id=category.age_group_id,
            category_name=category.name,
            start_number=qualification.start_number,
            full_name=" ".join(filter(None, (qualification.surname, qualification.name, qualification.patronymic))),
            club=club_names.get(result.participant_id, qualification.club),
            qualification_place=qualification.place,
            exit_order=qualification.exit_order,
            version=result.version,
            locked=attempt is not None,
            zone_attempt=attempt.zone_attempt if attempt else None,
            top_attempt=attempt.top_attempt if attempt else None,
            score=route_score_tenths(attempt.zone_attempt, attempt.top_attempt) / 10 if attempt else 0,
        ))
    participants.sort(key=lambda item: (item.category_name, item.exit_order or 10_000, item.start_number))
    return JudgeWorkspaceResponse(
        event_id=event.id, event_title=event.title, stage=event.stage,
        route=JudgeFinalRouteRead(id=route.id, number=route.number, name=route.name),
        participants=participants,
        conflicts=[{
            "id": str(conflict.id), "final_result_id": str(conflict.final_result_id),
            **json.loads(conflict.details_json),
        } for conflict in db.scalars(select(JudgeResultConflict).where(
            JudgeResultConflict.event_id == event.id,
            JudgeResultConflict.final_route_id == route.id,
            JudgeResultConflict.resolution.is_(None),
        )).all()],
    )


@router.get("/workspace", response_model=JudgeWorkspaceResponse)
def read_workspace(
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> JudgeWorkspaceResponse:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    ensure_final_active(event)
    return workspace_response(db, event, assigned_final_route(db, event, admin))


@router.put("/results/{final_result_id}", response_model=JudgeWorkspaceResponse)
def save_result(
    final_result_id: uuid.UUID, payload: JudgeResultCreate, operation_id: OperationId,
    preserve_conflict: bool = False,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> JudgeWorkspaceResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update(read=True))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    ensure_final_active(event)
    route = assigned_final_route(db, event, admin)
    category_id = db.scalar(select(FinalCategoryResult.category_snapshot_id).where(
        FinalCategoryResult.id == final_result_id,
        FinalCategoryResult.event_id == event.id,
    ))
    if category_id is None:
        raise HTTPException(status_code=404, detail="Финалист не найден")
    # Take the shared category lock BEFORE any finalist lock. Recalculation
    # touches all places, so independent judges need one consistent lock order.
    category = db.scalar(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.id == category_id).with_for_update()
        .execution_options(populate_existing=True))
    final_result = db.scalar(select(FinalCategoryResult).where(
        FinalCategoryResult.id == final_result_id).with_for_update().execution_options(populate_existing=True))
    if category is None or final_result is None:
        raise HTTPException(status_code=404, detail="Финалист не найден")
    assignment = db.scalar(select(FinalCategoryRoute).where(
        FinalCategoryRoute.event_id == event.id,
        FinalCategoryRoute.age_group_id == category.age_group_id,
        FinalCategoryRoute.final_route_id == route.id,
    ))
    if not assignment:
        raise HTTPException(status_code=403, detail="Эта трасса не назначена возрастной категории участника")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="judge.result.create",
        target_type="participant", target_id=str(final_result.participant_id),
        payload={**payload.model_dump(mode="json"), "final_route_id": str(route.id)},
    )
    if replay is not None:
        return replay
    # This endpoint only inserts a first attempt on the assigned route. The
    # aggregate version can change when another judge saves another route;
    # the route's existing-attempt check below is the actual overwrite guard.
    existing = db.scalar(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id == final_result.id,
        FinalRouteAttempt.final_route_id == route.id,
    ))
    if existing:
        if not preserve_conflict:
            raise HTTPException(status_code=409, detail="Результат уже сохранен и заблокирован для судьи")
        conflict_id = None
        if (existing.zone_attempt, existing.top_attempt) != (payload.zone_attempt, payload.top_attempt):
            snapshot = db.get(QualificationResultSnapshot, final_result.qualification_result_snapshot_id)
            details = {
                "start_number": snapshot.start_number,
                "full_name": " ".join(filter(None, (snapshot.surname, snapshot.name, snapshot.patronymic))),
                "route_name": route.name, "judge_name": admin.full_name,
                "submitted": {"zone_attempt": payload.zone_attempt, "top_attempt": payload.top_attempt},
                "server_at_submission": {"zone_attempt": existing.zone_attempt, "top_attempt": existing.top_attempt},
            }
            conflict_id = operation_id
            db.add(JudgeResultConflict(
                id=conflict_id, event_id=event.id, final_result_id=final_result.id,
                final_route_id=route.id, actor_id=admin.id,
                details_json=json.dumps(details, ensure_ascii=False),
            ))
            write_audit(db, actor=admin, action="judge.result.conflict", target_type="participant",
                        target_id=str(final_result.participant_id), old_value=details["server_at_submission"],
                        new_value={**details, "conflict_id": str(conflict_id)})
            db.flush()
        response = workspace_response(db, event, route).model_dump(mode="json")
        response["submission_conflict_id"] = str(conflict_id) if conflict_id else None
        complete_operation(record, response)
        db.commit()
        return response
    db.add(FinalRouteAttempt(
        event_id=event.id, final_category_result_id=final_result.id, final_route_id=route.id,
        zone_attempt=payload.zone_attempt, top_attempt=payload.top_attempt,
    ))
    final_result.version += 1
    db.flush()
    route_ids = list(db.scalars(select(FinalCategoryRoute.final_route_id).where(
        FinalCategoryRoute.event_id == event.id,
        FinalCategoryRoute.age_group_id == category.age_group_id,
    )).all())
    if len(route_ids) != 4:
        raise HTTPException(status_code=409, detail="Для категории должны быть назначены четыре финальные трассы")
    recalculate_final_category(db, category.id, route_ids)
    db.flush()
    response = workspace_response(db, event, route).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response
