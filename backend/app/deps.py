import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Admin, UserAccess
from app.security import decode_token_claims

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_admin(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Admin:
    claims = decode_token_claims(token) or {}
    subject = claims.get("sub")
    try:
        admin_id = uuid.UUID(subject or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход") from exc
    admin = db.get(Admin, admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    access = db.get(UserAccess, admin_id)
    if not access or not claims.get("sid"):
        raise HTTPException(401, detail="Сеанс завершён. Войдите снова.")
    if str(access.session_id) != claims["sid"]:
        message = "Выполнен вход на другом устройстве." if access.session_id else "Сеанс завершён администратором."
        raise HTTPException(401, detail=message)
    if not access.session_expires_at or access.session_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, detail="Срок сеанса истёк. Войдите снова.")
    request.state.session_id = access.session_id
    from app.permissions import Permission, effective_permissions
    if Permission.system_read_only in effective_permissions(db, admin.role):
        if (request.method not in {"GET", "HEAD"} and request.url.path not in {"/api/v1/auth/logout", "/api/v1/auth/heartbeat"}) or (request.url.path.startswith("/api/v1/admin/backups/") and request.url.path.endswith("/download")):
            raise HTTPException(status_code=403, detail="Доступен только просмотр. Изменение данных запрещено.")
    return admin
