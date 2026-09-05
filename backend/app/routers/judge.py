import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import (
    Admin, Event, EventStage, FinalCategoryResult, FinalCategoryRoute, FinalRoute,
    FinalRouteAttempt, QualificationCategorySnapshot, QualificationResultSnapshot,
)
from app.operations import OperationId, begin_operation, complete_operation, require_version
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
            club=qualification.club,
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
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> JudgeWorkspaceResponse | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    ensure_final_active(event)
    route = assigned_final_route(db, event, admin)
    final_result = db.scalar(select(FinalCategoryResult).where(
        FinalCategoryResult.id == final_result_id,
        FinalCategoryResult.event_id == event.id,
    ).with_for_update())
    if not final_result:
        raise HTTPException(status_code=404, detail="Финалист не найден")
    category = db.get(QualificationCategorySnapshot, final_result.category_snapshot_id)
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
    require_version(final_result, payload.expected_version)
    existing = db.scalar(select(FinalRouteAttempt).where(
        FinalRouteAttempt.final_category_result_id == final_result.id,
        FinalRouteAttempt.final_route_id == route.id,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="Результат уже сохранен и заблокирован для судьи")
    db.add(FinalRouteAttempt(
        event_id=event.id, final_category_result_id=final_result.id, final_route_id=route.id,
        zone_attempt=payload.zone_attempt, top_attempt=payload.top_attempt,
    ))
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
