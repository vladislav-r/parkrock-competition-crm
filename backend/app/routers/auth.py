from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.audit import write_audit
from app.models import Admin, UserAccess, UserPresence
from app.permissions import effective_permissions
from app.schemas import AdminRead, Token
from app.security import verify_password
from app.sessions import access_for, credential_hash, end_session, lock_user, rate_limit_qr, start_session

router = APIRouter(prefix="/auth", tags=["auth"])


class ConnectionReport(BaseModel):
    latency_ms: int = Field(ge=0, le=60000)
    unstable: bool = False


@router.get("/heartbeat")
def probe(_: Admin = Depends(get_current_admin)) -> dict[str, str]:
    return {"status": "ok"}


@router.post("/heartbeat")
def heartbeat(report: ConnectionReport, admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    # Only the authenticated account can report its own connection.
    values = dict(last_seen=func.now(), latency_ms=report.latency_ms, unstable=report.unstable)
    db.execute(insert(UserPresence).values(user_id=admin.id, **values).on_conflict_do_update(
        index_elements=[UserPresence.user_id], set_=values,
    ))
    db.commit()
    return {"status": "ok"}


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    admin = db.scalar(select(Admin).where(Admin.email == form.username.lower()).with_for_update())
    if not admin or not admin.is_active or not verify_password(form.password, admin.password_hash):
        write_audit(
            db, actor=admin, action="auth.login", target_type="session",
            target_id=form.username.lower(), result="denied",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная почта или пароль")
    write_audit(db, actor=admin, action="auth.login", target_type="session", result="success")
    token = start_session(db, admin)
    db.commit()
    return Token(access_token=token)


class QrCredential(BaseModel):
    key: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")


def qr_user(payload: QrCredential, db: Session) -> Admin:
    user_id = db.scalar(select(UserAccess.user_id).where(UserAccess.qr_hash == credential_hash(payload.key)))
    user = lock_user(db, user_id) if user_id else None
    # Recheck after locking: revoke/rotation and login must never cross each other.
    access = access_for(db, user) if user else None
    if not user or not user.is_active or not access or access.qr_hash != credential_hash(payload.key):
        write_audit(db, actor=None, action="auth.qr.login", target_type="session", result="denied")
        db.commit()
        raise HTTPException(401, "QR-код недействителен или доступ отключён. Обратитесь к администратору.")
    return user


@router.post("/qr/preview")
def preview_qr(payload: QrCredential, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    rate_limit_qr(db, request)
    response.headers["Cache-Control"] = "no-store"
    user = qr_user(payload, db)
    return {"full_name": user.full_name, "qr_session_hours": access_for(db, user).qr_session_hours}


@router.post("/qr/login", response_model=Token)
def login_qr(payload: QrCredential, request: Request, response: Response, db: Session = Depends(get_db)) -> Token:
    rate_limit_qr(db, request)
    response.headers["Cache-Control"] = "no-store"
    user = qr_user(payload, db)
    token = start_session(db, user, qr=True)
    write_audit(db, actor=user, action="auth.qr.login", target_type="session", result="success")
    db.commit()
    return Token(access_token=token)


@router.get("/me", response_model=AdminRead)
def me(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> AdminRead:
    return AdminRead(
        id=admin.id, email=admin.email, full_name=admin.full_name, role=admin.role,
        assigned_route_id=admin.assigned_route_id, assigned_final_route_id=admin.assigned_final_route_id,
        permissions=sorted(item.value for item in effective_permissions(db, admin.role)),
    )


@router.post("/logout")
def logout(request: Request, admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    lock_user(db, admin.id)
    access = access_for(db, admin)
    if access.session_id == request.state.session_id:
        end_session(db, access, "logout")
    write_audit(db, actor=admin, action="auth.logout", target_type="session")
    db.commit()
    return {"status": "ok"}
