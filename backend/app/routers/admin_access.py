import base64
import hashlib
import hmac
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, UserAccess, UserRole
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.qr_cards import printable_cards
from app.sessions import access_for, access_status, credential_hash, end_session, lock_user

router = APIRouter(prefix="/admin/users", tags=["admin-access"])


def administrator(actor: Admin = Depends(get_current_admin)) -> Admin:
    if actor.role != UserRole.administrator:
        raise HTTPException(403, "Управление QR и сеансами доступно только администратору")
    return actor


class AccessChange(BaseModel):
    expected_version: int = Field(ge=1)
    qr_session_hours: int = Field(default=12, ge=1, le=168)
    end_session: bool = False


class SessionEnd(BaseModel):
    session_id: uuid.UUID


class CardUser(BaseModel):
    user_id: uuid.UUID
    expected_version: int = Field(ge=1)


class IssueCards(BaseModel):
    users: list[CardUser] = Field(min_length=1, max_length=100)
    origin: str = Field(max_length=250)
    end_session: bool = False

    @model_validator(mode="after")
    def unique_users(self):
        if len({item.user_id for item in self.users}) != len(self.users):
            raise ValueError("Повторяющиеся пользователи")
        return self


@router.get("/access")
def list_access(response: Response, db: Session = Depends(get_db), actor: Admin = Depends(administrator)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    rows = {row.user_id: row for row in db.scalars(select(UserAccess)).all()}
    return {str(user_id): access_status(rows.get(user_id)) for user_id in db.scalars(select(Admin.id)).all()}


@router.post("/qr/issue")
def issue_cards(payload: IssueCards, operation_id: OperationId, response: Response,
                db: Session = Depends(get_db), actor: Admin = Depends(administrator)) -> dict:
    origin = payload.origin.rstrip("/")
    parsed = urlsplit(origin)
    if origin not in {item.rstrip("/") for item in settings.cors_origins} or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise HTTPException(422, "Адрес сайта должен совпадать с настроенным адресом приложения")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}):
        raise HTTPException(422, "Для печатного QR требуется HTTPS")
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=actor.id, action="user.qr.issue",
                                    target_type="qr_batch", target_id=str(operation_id), payload=payload.model_dump(mode="json"))
    users, keys, states = [], {}, {}
    for item in sorted(payload.users, key=lambda row: str(row.user_id)):
        user = lock_user(db, item.user_id)
        if not user.is_active:
            raise HTTPException(409, f"Учётная запись «{user.full_name}» отключена")
        access = access_for(db, user)
        # Stable secret for a transport retry, without storing it in operation/audit records.
        secret = hmac.new(settings.jwt_secret.encode(), f"parkrock-qr:{operation_id}:{user.id}".encode(), hashlib.sha256).digest()
        key = base64.urlsafe_b64encode(secret).decode().rstrip("=")
        if replay is None:
            require_version(access, item.expected_version)
            access.qr_hash = credential_hash(key)
            access.version += 1
            if payload.end_session:
                end_session(db, access)
        elif access.qr_hash != credential_hash(key):
            raise HTTPException(409, "QR уже отозван или перевыпущен. Обновите список пользователей.")
        users.append(user)
        keys[user.id] = key
        states[str(user.id)] = {"full_name": user.full_name, **access_status(access)}
    result = printable_cards(users, keys, origin)
    if replay is None:
        complete_operation(record, {"users": states, "sessions_ended": payload.end_session})
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return result


@router.put("/{user_id}/qr/settings")
def qr_settings(user_id: uuid.UUID, payload: AccessChange, operation_id: OperationId,
                db: Session = Depends(get_db), actor: Admin = Depends(administrator)) -> dict:
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=actor.id, action="user.qr.settings",
                                    target_type="user", target_id=str(user_id), payload=payload.model_dump())
    if replay is not None:
        return replay
    access = access_for(db, lock_user(db, user_id))
    require_version(access, payload.expected_version)
    access.qr_session_hours = payload.qr_session_hours
    access.version += 1
    result = access_status(access)
    complete_operation(record, result)
    db.commit()
    return result


@router.post("/{user_id}/qr/revoke")
def revoke_qr(user_id: uuid.UUID, payload: AccessChange, operation_id: OperationId,
              db: Session = Depends(get_db), actor: Admin = Depends(administrator)) -> dict:
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=actor.id, action="user.qr.revoke",
                                    target_type="user", target_id=str(user_id), payload=payload.model_dump())
    if replay is not None:
        return replay
    access = access_for(db, lock_user(db, user_id))
    require_version(access, payload.expected_version)
    access.qr_hash = None
    access.version += 1
    if payload.end_session:
        end_session(db, access)
    result = access_status(access)
    complete_operation(record, result)
    db.commit()
    return result


@router.post("/{user_id}/session/end")
def terminate_session(user_id: uuid.UUID, payload: SessionEnd, operation_id: OperationId,
                      db: Session = Depends(get_db), actor: Admin = Depends(administrator)) -> dict:
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=actor.id, action="user.session.end",
                                    target_type="user", target_id=str(user_id), payload=payload.model_dump(mode="json"))
    if replay is not None:
        return replay
    access = access_for(db, lock_user(db, user_id))
    if access.session_id != payload.session_id:
        raise HTTPException(409, "Сеанс пользователя изменился. Обновите список и повторите действие.")
    end_session(db, access)
    result = access_status(access)
    complete_operation(record, result)
    db.commit()
    return result
