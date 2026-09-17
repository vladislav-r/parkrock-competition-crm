from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.audit import write_audit
from app.models import Admin, UserPresence
from app.permissions import effective_permissions
from app.schemas import AdminRead, Token
from app.security import create_access_token, verify_password

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
    admin = db.scalar(select(Admin).where(Admin.email == form.username.lower()))
    if not admin or not admin.is_active or not verify_password(form.password, admin.password_hash):
        write_audit(
            db, actor=admin, action="auth.login", target_type="session",
            target_id=form.username.lower(), result="denied",
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная почта или пароль")
    write_audit(db, actor=admin, action="auth.login", target_type="session", result="success")
    db.commit()
    return Token(access_token=create_access_token(str(admin.id)))


@router.get("/me", response_model=AdminRead)
def me(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> AdminRead:
    return AdminRead(
        id=admin.id, email=admin.email, full_name=admin.full_name, role=admin.role,
        assigned_route_id=admin.assigned_route_id, assigned_final_route_id=admin.assigned_final_route_id,
        permissions=sorted(item.value for item in effective_permissions(db, admin.role)),
    )


@router.post("/logout")
def logout(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    write_audit(db, actor=admin, action="auth.logout", target_type="session")
    db.commit()
    return {"status": "ok"}
