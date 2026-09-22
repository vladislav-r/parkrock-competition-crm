"""Session changes are serialized by the owning Admin row, independently of its edit version."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Admin, AuthRateLimit, UserAccess, UserPresence
from app.security import create_access_token


def credential_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def lock_user(db: Session, user_id: uuid.UUID) -> Admin:
    user = db.scalar(select(Admin).where(Admin.id == user_id).with_for_update().execution_options(populate_existing=True))
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


def access_for(db: Session, user: Admin) -> UserAccess:
    access = db.get(UserAccess, user.id, populate_existing=True)
    if access is None:
        access = UserAccess(user_id=user.id, qr_session_hours=12, version=1)
        db.add(access)
        db.flush()
    return access


def start_session(db: Session, user: Admin, *, qr: bool = False) -> str:
    # Caller holds the Admin row lock through commit.
    access = access_for(db, user)
    access.session_id = uuid.uuid4()
    access.session_expires_at = datetime.now(timezone.utc) + (
        timedelta(hours=access.qr_session_hours) if qr else timedelta(minutes=settings.access_token_expire_minutes)
    )
    access.session_end_reason = None
    db.execute(delete(UserPresence).where(UserPresence.user_id == user.id))
    return create_access_token(str(user.id), str(access.session_id), access.session_expires_at)


def end_session(db: Session, access: UserAccess, reason: str = "revoked") -> None:
    access.session_id = None
    access.session_expires_at = None
    access.session_end_reason = reason
    db.execute(delete(UserPresence).where(UserPresence.user_id == access.user_id))


def access_status(access: UserAccess | None) -> dict:
    active = bool(access and access.session_id and access.session_expires_at > datetime.now(timezone.utc))
    return dict(qr_enabled=bool(access and access.qr_hash), qr_session_hours=access.qr_session_hours if access else 12,
                version=access.version if access else 1, session_id=str(access.session_id) if active else None,
                session_expires_at=access.session_expires_at.isoformat() if active else None)


def rate_limit_qr(db: Session, request: Request) -> None:
    # PostgreSQL makes the limit shared by all workers. No credentials or raw IPs are retained.
    key = credential_hash("qr:" + (request.client.host if request.client else "unknown"))
    now = datetime.now(timezone.utc)
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at < now))
    expired = AuthRateLimit.expires_at <= now
    statement = insert(AuthRateLimit).values(key=key, attempts=1, expires_at=now + timedelta(minutes=1))
    attempts = db.scalar(statement.on_conflict_do_update(index_elements=[AuthRateLimit.key], set_={
        "attempts": case((expired, 1), else_=AuthRateLimit.attempts + 1),
        "expires_at": case((expired, now + timedelta(minutes=1)), else_=AuthRateLimit.expires_at),
    }).returning(AuthRateLimit.attempts))
    db.commit()
    if attempts > 30:
        raise HTTPException(429, "Слишком много попыток. Повторите через минуту.", headers={"Retry-After": "60"})
