from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import backup_service
from app.audit import write_audit
from app.permissions import Permission, require_permission
from app.db import get_db
from app.deps import get_current_admin
from app.models import (
    Admin, AgeGroup, ApplicationFile, Ascent, Club, CompetitionSet, Event, EventStage,
    FinalCategoryResult, FinalCategoryRoute, FinalRoute, FinalRouteAttempt, Participant,
    PublishedResult, QualificationCategorySnapshot, QualificationResultSnapshot, Route,
    RouteGradePoint, SetStatus, UserRole,
)


router = APIRouter(prefix="/admin/competition", tags=["admin-competition"])

ResetTarget = Literal[
    "stage", "qualification_results", "final_results", "final_setup", "applications",
    "participants", "reception", "clubs", "sets", "set_statuses", "routes", "categories",
    "judge_assignments", "publication", "all",
]

TARGET_LABELS: dict[str, str] = {
    "stage": "этап соревнования",
    "qualification_results": "результаты квалификации",
    "final_results": "результаты финала",
    "final_setup": "настройки финала",
    "applications": "заявки",
    "participants": "участников",
    "reception": "статусы ресепшена",
    "clubs": "клубы",
    "sets": "сеты",
    "set_statuses": "статусы сетов",
    "routes": "квалификационные трассы и таблицу баллов",
    "categories": "возрастные группы и медальные диапазоны",
    "judge_assignments": "назначения судей на трассы",
    "publication": "настройку публичных результатов",
    "all": "все данные соревнования",
}


class ResetRequest(BaseModel):
    target: ResetTarget
    confirmation: str


require_reset_access = require_permission(Permission.competition_reset)

def _event(db: Session) -> Event:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return event


def _is_test_database(db: Session) -> bool:
    return bool(db.bind and (make_url(str(db.bind.url)).database or "").endswith("_test"))


def _backup(db: Session, event: Event, *, source: str, note: str, target: str) -> dict:
    if _is_test_database(db):
        return {"filename": f"test-{source}-{target}.dump", "note": note}
    return backup_service.create_backup(
        db, source=source, note=note,
        context={"event_id": str(event.id), "target": target, "kind": "competition-reset"},
    )


def _clear_final_results(db: Session, event: Event) -> int:
    deleted = db.scalar(select(func.count(FinalRouteAttempt.id)).where(FinalRouteAttempt.event_id == event.id)) or 0
    db.execute(delete(FinalRouteAttempt).where(FinalRouteAttempt.event_id == event.id))
    db.execute(update(FinalCategoryResult).where(FinalCategoryResult.event_id == event.id).values(
        score_tenths=0, top_count=0, zone_count=0, top_attempts=0, zone_attempts=0, place=None,
    ))
    if event.stage == EventStage.completed:
        event.stage = EventStage.final
        event.completed_at = None
    return deleted


def _clear_final_setup(db: Session, event: Event) -> int:
    attempts = _clear_final_results(db, event)
    assignments = db.scalar(select(func.count(FinalCategoryRoute.id)).where(FinalCategoryRoute.event_id == event.id)) or 0
    db.execute(delete(FinalCategoryRoute).where(FinalCategoryRoute.event_id == event.id))
    return attempts + assignments


def _clear_qualification_results(db: Session, event: Event) -> int:
    participant_ids = select(Participant.id).where(Participant.event_id == event.id)
    deleted = db.scalar(select(func.count(Ascent.id)).where(Ascent.participant_id.in_(participant_ids))) or 0
    _clear_final_setup(db, event)
    db.execute(delete(QualificationResultSnapshot).where(QualificationResultSnapshot.event_id == event.id))
    db.execute(delete(QualificationCategorySnapshot).where(QualificationCategorySnapshot.event_id == event.id))
    db.execute(delete(PublishedResult).where(PublishedResult.event_id == event.id))
    db.execute(delete(Ascent).where(Ascent.participant_id.in_(participant_ids)))
    groups = db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id)).all()
    for group in groups:
        group.qualification_confirmed_at = None
        group.qualification_confirmed_by_id = None
        group.qualification_signature = None
    event.stage = EventStage.qualification
    event.final_started_at = None
    event.completed_at = None
    return deleted


def _return_to_preparation(db: Session, event: Event) -> int:
    deleted = _clear_qualification_results(db, event)
    event.stage = EventStage.preparation
    event.qualification_started_at = None
    return deleted


def _counts(db: Session, event: Event) -> dict[str, int]:
    participant_ids = select(Participant.id).where(Participant.event_id == event.id)
    return {
        "applications": db.scalar(select(func.count(ApplicationFile.id)).where(ApplicationFile.event_id == event.id)) or 0,
        "participants": db.scalar(select(func.count(Participant.id)).where(Participant.event_id == event.id)) or 0,
        "reception": db.scalar(select(func.count(Participant.id)).where(
            Participant.event_id == event.id,
            or_(Participant.checked_in_at.is_not(None), Participant.is_paid.is_(True), Participant.merch_issued.is_(True)),
        )) or 0,
        "clubs": db.scalar(select(func.count(Club.id)).where(Club.event_id == event.id)) or 0,
        "sets": db.scalar(select(func.count(CompetitionSet.id)).where(CompetitionSet.event_id == event.id)) or 0,
        "set_statuses": db.scalar(select(func.count(CompetitionSet.id)).where(
            CompetitionSet.event_id == event.id, CompetitionSet.status != SetStatus.draft,
        )) or 0,
        "routes": db.scalar(select(func.count(Route.id)).where(Route.event_id == event.id)) or 0,
        "categories": db.scalar(select(func.count(AgeGroup.id)).where(AgeGroup.event_id == event.id)) or 0,
        "qualification_results": db.scalar(select(func.count(Ascent.id)).where(Ascent.participant_id.in_(participant_ids))) or 0,
        "final_results": db.scalar(select(func.count(FinalRouteAttempt.id)).where(FinalRouteAttempt.event_id == event.id)) or 0,
        "final_setup": db.scalar(select(func.count(FinalCategoryRoute.id)).where(FinalCategoryRoute.event_id == event.id)) or 0,
        "judge_assignments": db.scalar(select(func.count(Admin.id)).where(or_(
            Admin.assigned_route_id.is_not(None), Admin.assigned_final_route_id.is_not(None),
        ))) or 0,
        "publication": 1 if event.public_result_details_enabled else 0,
    }


@router.get("/reset-status")
def reset_status(db: Session = Depends(get_db), _: Admin = Depends(require_reset_access)):
    event = _event(db)
    return {"stage": event.stage.value, "qualification_started": bool(event.qualification_started_at), "counts": _counts(db, event)}


@router.post("/reset")
def reset_competition(
    payload: ResetRequest,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_reset_access),
):
    if payload.confirmation != "СБРОСИТЬ":
        raise HTTPException(status_code=422, detail="Подтверждение сброса не получено")
    event = _event(db)
    label = TARGET_LABELS[payload.target]
    locked = False
    try:
        if not _is_test_database(db):
            locked = backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False)
            if not locked:
                raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
        before = _counts(db, event)
        if payload.target == "clubs" and before["participants"]:
            raise HTTPException(status_code=409, detail="Сначала сбросьте участников: они связаны с клубами")
        if payload.target == "sets" and before["participants"]:
            raise HTTPException(status_code=409, detail="Сначала сбросьте участников: они распределены по сетам")
        safety = _backup(
            db, event, source="pre-reset",
            note=f"ДО СБРОСА: {label}", target=payload.target,
        )

        deleted = 0
        if payload.target == "stage":
            deleted = _return_to_preparation(db, event)
        elif payload.target == "qualification_results":
            deleted = _clear_qualification_results(db, event)
        elif payload.target == "final_results":
            deleted = _clear_final_results(db, event)
        elif payload.target == "final_setup":
            deleted = _clear_final_setup(db, event)
        elif payload.target == "applications":
            deleted = before["applications"]
            db.execute(delete(ApplicationFile).where(ApplicationFile.event_id == event.id))
        elif payload.target == "participants":
            _return_to_preparation(db, event)
            deleted = before["participants"]
            db.execute(delete(Participant).where(Participant.event_id == event.id))
        elif payload.target == "reception":
            deleted = before["reception"]
            db.execute(update(Participant).where(Participant.event_id == event.id).values(
                checked_in_at=None, is_paid=False, merch_issued=False,
            ))
        elif payload.target == "clubs":
            deleted = before["clubs"]
            db.execute(delete(Club).where(Club.event_id == event.id))
        elif payload.target == "sets":
            _return_to_preparation(db, event)
            deleted = before["sets"]
            db.execute(delete(CompetitionSet).where(CompetitionSet.event_id == event.id))
        elif payload.target == "set_statuses":
            deleted = before["set_statuses"]
            db.execute(update(CompetitionSet).where(CompetitionSet.event_id == event.id).values(
                status=SetStatus.draft, confirmed_at=None,
            ))
        elif payload.target == "routes":
            _return_to_preparation(db, event)
            deleted = before["routes"]
            db.execute(update(Admin).where(Admin.assigned_route_id.is_not(None)).values(assigned_route_id=None))
            db.execute(delete(RouteGradePoint).where(RouteGradePoint.event_id == event.id))
            db.execute(delete(Route).where(Route.event_id == event.id))
        elif payload.target == "categories":
            _return_to_preparation(db, event)
            deleted = before["categories"]
            db.execute(delete(AgeGroup).where(AgeGroup.event_id == event.id))
        elif payload.target == "judge_assignments":
            deleted = before["judge_assignments"]
            db.execute(update(Admin).where(or_(
                Admin.assigned_route_id.is_not(None), Admin.assigned_final_route_id.is_not(None),
            )).values(assigned_route_id=None, assigned_final_route_id=None))
        elif payload.target == "publication":
            deleted = before["publication"]
            event.public_result_details_enabled = False
        else:
            _return_to_preparation(db, event)
            deleted = sum(before[key] for key in ("applications", "participants", "clubs", "sets", "routes", "categories"))
            db.execute(delete(ApplicationFile).where(ApplicationFile.event_id == event.id))
            db.execute(delete(Participant).where(Participant.event_id == event.id))
            db.execute(delete(Club).where(Club.event_id == event.id))
            db.execute(delete(RouteGradePoint).where(RouteGradePoint.event_id == event.id))
            db.execute(delete(Route).where(Route.event_id == event.id))
            db.execute(delete(CompetitionSet).where(CompetitionSet.event_id == event.id))
            db.execute(delete(AgeGroup).where(AgeGroup.event_id == event.id))
            db.execute(update(Admin).where(or_(
                Admin.assigned_route_id.is_not(None), Admin.assigned_final_route_id.is_not(None),
            )).values(assigned_route_id=None, assigned_final_route_id=None))
            db.execute(delete(FinalRoute).where(FinalRoute.event_id == event.id))
            event.public_result_details_enabled = False

        write_audit(
            db, actor=admin, action="competition.reset", target_type="competition-data",
            target_id=payload.target, old_value=before,
            new_value={"target": payload.target, "deleted": deleted, "safety_backup": safety["filename"]},
        )
        db.commit()
        zero_backup = None
        if payload.target == "all":
            try:
                zero_backup = _backup(
                    db, event, source="factory-zero",
                    note="Нулевой снимок · заводское состояние", target="all",
                )
            except backup_service.BackupError as error:
                raise HTTPException(status_code=503, detail=f"Сброс выполнен, но нулевой снимок не создан: {error}") from error
        return {
            "status": "reset", "target": payload.target, "deleted": deleted,
            "safety_backup": safety["filename"],
            "zero_backup": zero_backup["filename"] if zero_backup else None,
        }
    except backup_service.BackupError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Сброс отменён: резервная копия не создана. {error}") from error
    finally:
        if locked:
            backup_service.BACKUP_OPERATION_LOCK.release()
