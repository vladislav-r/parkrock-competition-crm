import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, CompetitionSet, Event, Participant, SetStatus
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.routers.public import set_read
from app.schemas import SetCreate, SetRead, SetUpdate, VersionedAction
from app.services import publish_set


router = APIRouter(prefix="/admin", tags=["admin-sets"], dependencies=[Depends(require_permission(Permission.sets_manage))])


def validate_set_payload(payload: SetCreate | SetUpdate) -> tuple[str, str]:
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=422, detail="Время окончания сета должно быть позже времени начала")
    return payload.start_time.strftime("%H:%M"), payload.end_time.strftime("%H:%M")


def ensure_qualification(db: Session, event_id) -> None:
    if db.get(Event, event_id).final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала управление сетами заблокировано")


@router.post("/sets", response_model=SetRead)
def create_set(
    payload: SetCreate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> SetRead | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    ensure_qualification(db, event.id)
    set_id = uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:set:{operation_id}")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="set.create",
        target_type="set", target_id=str(set_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    name = payload.name.strip()
    duplicate = db.scalar(select(CompetitionSet).where(
        CompetitionSet.event_id == event.id, func.lower(CompetitionSet.name) == name.lower()))
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Сет с названием «{name}» уже существует")
    start_time, end_time = validate_set_payload(payload)
    competition_set = CompetitionSet(
        id=set_id, event_id=event.id, name=name, scheduled_on=payload.scheduled_on,
        time_label=f"{start_time}-{end_time}",
        capacity=payload.capacity, status=SetStatus.draft,
    )
    db.add(competition_set)
    db.flush()
    response = SetRead(**set_read(db, competition_set).model_dump(), version=competition_set.version).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.patch("/sets/{set_id}", response_model=SetRead)
def update_set(
    set_id: uuid.UUID,
    payload: SetUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> SetRead | dict:
    competition_set = db.get(CompetitionSet, set_id)
    if not competition_set:
        raise HTTPException(status_code=404, detail="Сет не найден")
    ensure_qualification(db, competition_set.event_id)
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="set.update",
        target_type="set", target_id=str(set_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(competition_set, payload.expected_version)
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Сет подтвержден. Сначала откройте его для редактирования")
    name = payload.name.strip()
    duplicate = db.scalar(select(CompetitionSet).where(
        CompetitionSet.event_id == competition_set.event_id, CompetitionSet.id != competition_set.id,
        func.lower(CompetitionSet.name) == name.lower(),
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Сет с названием «{name}» уже существует")
    participant_count = db.scalar(select(func.count()).select_from(Participant).where(
        Participant.set_id == competition_set.id, Participant.archived_at.is_(None))) or 0
    if payload.capacity < participant_count:
        raise HTTPException(status_code=409, detail=f"Нельзя установить вместимость {payload.capacity}: в сете уже назначено участников: {participant_count}")
    start_time, end_time = validate_set_payload(payload)
    competition_set.name = name
    competition_set.scheduled_on = payload.scheduled_on
    competition_set.time_label = f"{start_time}-{end_time}"
    competition_set.capacity = payload.capacity
    db.flush()
    response = SetRead(**set_read(db, competition_set).model_dump(), version=competition_set.version).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.delete("/sets/{set_id}")
def delete_set(
    set_id: uuid.UUID,
    operation_id: OperationId,
    expected_version: int = Query(ge=1),
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, str]:
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="set.delete",
        target_type="set", target_id=str(set_id), payload={"expected_version": expected_version},
    )
    if replay is not None:
        return replay
    competition_set = db.get(CompetitionSet, set_id)
    if not competition_set:
        raise HTTPException(status_code=404, detail="Сет не найден")
    ensure_qualification(db, competition_set.event_id)
    require_version(competition_set, expected_version)
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Подтвержденный сет нельзя удалить. Сначала откройте его")
    participant_count = db.scalar(select(func.count()).select_from(Participant).where(
        Participant.set_id == competition_set.id, Participant.archived_at.is_(None))) or 0
    if participant_count:
        raise HTTPException(status_code=409, detail=f"Нельзя удалить сет: в нем назначено участников: {participant_count}")
    response = {"status": "deleted"}
    complete_operation(record, response)
    db.delete(competition_set)
    db.commit()
    return response


@router.post("/sets/{set_id}/confirm")
def confirm_set(
    set_id: uuid.UUID,
    payload: VersionedAction,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, str]:
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="set.confirm",
        target_type="set", target_id=str(set_id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    competition_set = db.get(CompetitionSet, set_id)
    if not competition_set:
        raise HTTPException(status_code=404, detail="Сет не найден")
    ensure_qualification(db, competition_set.event_id)
    require_version(competition_set, payload.expected_version)
    publish_set(db, competition_set.id)
    competition_set.status = SetStatus.confirmed
    competition_set.confirmed_at = datetime.now(timezone.utc)
    response = {"status": "confirmed"}
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/sets/{set_id}/reopen")
def reopen_set(
    set_id: uuid.UUID,
    payload: VersionedAction,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, str]:
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="set.reopen",
        target_type="set", target_id=str(set_id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    competition_set = db.get(CompetitionSet, set_id)
    if not competition_set:
        raise HTTPException(status_code=404, detail="Сет не найден")
    ensure_qualification(db, competition_set.event_id)
    require_version(competition_set, payload.expected_version)
    competition_set.status = SetStatus.reopened
    response = {"status": "reopened"}
    complete_operation(record, response)
    db.commit()
    return response
