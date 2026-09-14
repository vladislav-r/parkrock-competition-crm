import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Admin
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_admin(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Admin:
    subject = decode_access_token(token)
    try:
        admin_id = uuid.UUID(subject or "")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход") from exc
    admin = db.get(Admin, admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход")
    from app.permissions import Permission, effective_permissions
    if Permission.system_read_only in effective_permissions(db, admin.role):
        if (request.method not in {"GET", "HEAD"} and request.url.path != "/api/v1/auth/logout") or (request.url.path.startswith("/api/v1/admin/backups/") and request.url.path.endswith("/download")):
            raise HTTPException(status_code=403, detail="Доступен только просмотр. Изменение данных запрещено.")
    return admin
