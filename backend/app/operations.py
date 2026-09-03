import hashlib
import json
import uuid
from typing import Annotated, Any

from fastapi import Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.audit import write_audit
from app.models import Admin, AgeGroup, ApplicationFile, Club, CompetitionSet, Event, OperationRecord, Participant, Route


OperationId = Annotated[uuid.UUID, Header(alias="X-Operation-Id")]


def require_version(entity: Any, expected_version: int) -> None:
    if entity.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "edit_conflict",
                "message": "Данные уже изменены на другом рабочем месте. Обновите страницу и повторите действие.",
                "current_version": entity.version,
            },
        )


def _request_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def begin_operation(
    db: Session,
    *,
    operation_id: uuid.UUID,
    admin_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: str,
    payload: Any,
) -> tuple[OperationRecord, dict[str, Any] | None]:
    request_hash = _request_hash(payload)
    existing = db.get(OperationRecord, operation_id)
    if existing:
        return existing, _validate_replay(existing, admin_id, action, target_type, target_id, request_hash)

    record = OperationRecord(
        id=operation_id,
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_hash=request_hash,
    )
    record._audit_old_value = _target_snapshot(db, target_type, target_id)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.get(OperationRecord, operation_id)
        if not existing:
            raise
        return existing, _validate_replay(existing, admin_id, action, target_type, target_id, request_hash)
    return record, None


def _validate_replay(
    record: OperationRecord,
    admin_id: uuid.UUID,
    action: str,
    target_type: str,
    target_id: str,
    request_hash: str,
) -> dict[str, Any]:
    if (
        record.admin_id != admin_id
        or record.action != action
        or record.target_type != target_type
        or record.target_id != target_id
        or record.request_hash != request_hash
    ):
        raise HTTPException(status_code=409, detail="Идентификатор операции уже использован для другого действия")
    if not record.response_json:
        raise HTTPException(status_code=409, detail="Операция с этим идентификатором еще выполняется")
    return json.loads(record.response_json)


def complete_operation(record: OperationRecord, response: Any) -> None:
    record.response_json = json.dumps(response, ensure_ascii=False, default=str, separators=(",", ":"))
    db = object_session(record)
    if db is not None:
        actor = db.get(Admin, record.admin_id)
        write_audit(
            db, actor=actor, action=record.action, target_type=record.target_type,
            target_id=record.target_id, old_value=getattr(record, "_audit_old_value", None), new_value=response,
            audit_id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:audit:{record.id}"),
        )


def _target_snapshot(db: Session, target_type: str, target_id: str) -> dict[str, Any] | None:
    model = {"user": Admin, "participant": Participant, "route": Route, "set": CompetitionSet,
             "club": Club, "event": Event, "age_group": AgeGroup, "application": ApplicationFile}.get(target_type)
    if not model:
        return None
    try:
        entity = db.get(model, uuid.UUID(target_id))
    except ValueError:
        return None
    if not entity:
        return None
    hidden = {"password_hash", "file_data"}
    return {
        column.name: getattr(entity, column.name)
        for column in entity.__table__.columns if column.name not in hidden
    }
