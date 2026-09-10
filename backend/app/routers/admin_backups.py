from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import backup_service
from app.audit import write_audit
from app.config import settings
from app.permissions import Permission, require_permission
from app.db import SessionLocal, get_db
from app.deps import get_current_admin
from app.models import Admin, UserRole


router = APIRouter(prefix="/admin/backups", tags=["admin-backups"])


class Confirmation(BaseModel):
    confirmation: str


require_backup_access = require_permission(Permission.backups_manage)

def service_error(error: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail={"code": "backup_error", "message": str(error)})


@router.get("")
def backups(db: Session = Depends(get_db), _: Admin = Depends(require_backup_access)):
    try:
        return backup_service.list_backups(db)
    except backup_service.BackupError as error:
        raise service_error(error) from error


@router.post("")
def create_backup(note: str = "", db: Session = Depends(get_db), admin: Admin = Depends(require_backup_access)):
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    try:
        item = backup_service.create_backup(db, note=note.strip()[:300])
        write_audit(db, actor=admin, action="backup.create", target_type="backup", target_id=item["filename"], new_value=item)
        db.commit()
        return item
    except backup_service.BackupError as error:
        raise service_error(error) from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()


@router.post("/upload")
def upload_backup(
    file: UploadFile = File(...), note: str = Form(default=""),
    db: Session = Depends(get_db), admin: Admin = Depends(require_backup_access),
):
    if not (file.filename or "").lower().endswith(".dump"):
        raise HTTPException(status_code=422, detail="Можно загрузить только файл PostgreSQL .dump")
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    path = None
    try:
        backup_service.BACKUP_DIRECTORY.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc)
        path = backup_service.BACKUP_DIRECTORY / f"climbhub-{timestamp.strftime('%Y%m%d-%H%M%S')}-upload.dump"
        size = 0
        with path.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.backup_max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"Файл больше {settings.backup_max_upload_mb} МБ")
                target.write(chunk)
        current = backup_service.current_summary(db)
        item = backup_service.verify_backup(path, current)
        metadata = backup_service._read_metadata(path)
        metadata.update({"source": "upload", "note": note.strip()[:300], "original_filename": file.filename})
        backup_service._write_metadata(path, metadata)
        item = backup_service.backup_item(path, current)
        write_audit(db, actor=admin, action="backup.upload", target_type="backup", target_id=item["filename"], new_value=item)
        db.commit()
        return item
    except HTTPException:
        if path:
            path.unlink(missing_ok=True)
            backup_service._metadata_path(path).unlink(missing_ok=True)
        raise
    except backup_service.BackupError as error:
        if path:
            path.unlink(missing_ok=True)
            backup_service._metadata_path(path).unlink(missing_ok=True)
        raise service_error(error) from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()


@router.get("/{filename}/download")
def download_backup(filename: str, _: Admin = Depends(require_backup_access)):
    try:
        path = backup_service.resolve_backup(filename)
        return FileResponse(path, media_type="application/octet-stream", filename=path.name)
    except backup_service.BackupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{filename}/verify")
def verify_backup(filename: str, db: Session = Depends(get_db), admin: Admin = Depends(require_backup_access)):
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    try:
        path = backup_service.resolve_backup(filename)
        item = backup_service.verify_backup(path, backup_service.current_summary(db))
        write_audit(db, actor=admin, action="backup.verify", target_type="backup", target_id=filename, new_value={"verified_at": item["verified_at"]})
        db.commit()
        return item
    except backup_service.BackupError as error:
        raise service_error(error) from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()


@router.delete("/{filename}")
def delete_backup(filename: str, payload: Confirmation, db: Session = Depends(get_db), admin: Admin = Depends(require_backup_access)):
    if payload.confirmation != "УДАЛИТЬ":
        raise HTTPException(status_code=422, detail="Введите УДАЛИТЬ для подтверждения")
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    try:
        path = backup_service.resolve_backup(filename)
        item = backup_service.backup_item(path)
        backup_service.delete_backup(path)
        write_audit(db, actor=admin, action="backup.delete", target_type="backup", target_id=filename, old_value=item)
        db.commit()
        return {"status": "deleted", "filename": filename}
    except backup_service.BackupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()


@router.post("/{filename}/restore")
def restore_backup(filename: str, payload: Confirmation, db: Session = Depends(get_db), admin: Admin = Depends(require_backup_access)):
    if payload.confirmation != f"ВОССТАНОВИТЬ {filename}":
        raise HTTPException(status_code=422, detail=f"Введите ВОССТАНОВИТЬ {filename} для подтверждения")
    if not backup_service.BACKUP_OPERATION_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="Уже выполняется операция с резервной копией")
    actor_id = admin.id
    try:
        path = backup_service.resolve_backup(filename)
        result = backup_service.restore_working_database(path, db)
        audit_db = SessionLocal()
        try:
            restored_actor = audit_db.get(Admin, actor_id)
            write_audit(
                audit_db, actor=restored_actor, action="backup.restore", target_type="backup", target_id=filename,
                new_value={"safety_backup": result["safety_backup"]["filename"]},
            )
            audit_db.commit()
        finally:
            audit_db.close()
        return result
    except backup_service.BackupError as error:
        raise service_error(error) from error
    finally:
        backup_service.BACKUP_OPERATION_LOCK.release()
