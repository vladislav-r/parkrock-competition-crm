import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, ApplicationFile, ApplicationType, Event
from app.operations import OperationId, begin_operation, complete_operation
from app.participant_import import analyze, create_participants_from_analysis, read_rows
from app.permissions import Permission, require_permission
from app.schemas import ApplicationRead
from app.telegram import send_application_document


public_router = APIRouter(prefix="/public/applications", tags=["applications"])
admin_router = APIRouter(
    prefix="/admin/applications", tags=["admin-applications"],
    dependencies=[Depends(require_permission(Permission.participants_import))],
)

MAX_APPLICATION_SIZE = 10 * 1024 * 1024
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM_CONTENT_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"


def application_read(item: ApplicationFile) -> ApplicationRead:
    return ApplicationRead.model_validate(item)


@public_router.post("", response_model=ApplicationRead, status_code=201)
async def submit_application(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    event = db.scalar(select(Event).where(Event.is_public.is_(True)).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Нет открытого фестиваля")
    filename = (file.filename or "").replace("\\", "/").split("/")[-1].strip()
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="Загрузите заполненный шаблон в формате XLSX или XLSM")
    content = await file.read(MAX_APPLICATION_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Файл заявки пуст")
    if len(content) > MAX_APPLICATION_SIZE:
        raise HTTPException(status_code=413, detail="Размер файла заявки не должен превышать 10 МБ")

    rows = read_rows(filename, content, strict_application_template=True)
    analysis = analyze(db, event, rows)
    if analysis.errors:
        preview = analysis.response()
        raise HTTPException(status_code=422, detail={
            "code": "invalid_application", "message": "В заявке есть ошибки. Исправьте файл и загрузите его снова.",
            **preview,
        })

    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(ApplicationFile).where(
        ApplicationFile.event_id == event.id, ApplicationFile.content_sha256 == digest,
    ))
    if existing:
        return application_read(existing)
    item = ApplicationFile(
        event_id=event.id, filename=filename,
        content_type=file.content_type or (XLSM_CONTENT_TYPE if filename.lower().endswith(".xlsm") else XLSX_CONTENT_TYPE),
        file_size=len(content), content_sha256=digest, file_data=content,
        participant_count=len(analysis.rows), duplicate_rows=analysis.duplicates,
        overflow_sets=len(analysis.overflow), status="pending",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ApplicationFile).where(
            ApplicationFile.event_id == event.id, ApplicationFile.content_sha256 == digest,
        ))
        if not existing:
            raise
        return application_read(existing)
    db.refresh(item)
    background_tasks.add_task(
        send_application_document,
        filename=item.filename,
        content=item.file_data,
        participant_count=item.participant_count,
    )
    return application_read(item)


@admin_router.get("", response_model=list[ApplicationRead])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationRead]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        return []
    items = db.scalars(select(ApplicationFile).where(
        ApplicationFile.event_id == event.id,
    ).order_by(ApplicationFile.uploaded_at.desc())).all()
    return [application_read(item) for item in items]


@admin_router.get("/{application_id}/download")
def download_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> Response:
    item = db.get(ApplicationFile, application_id)
    if not item:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    write_audit(
        db, actor=admin, action="application.download", target_type="application",
        target_id=str(item.id), new_value={"filename": item.filename},
    )
    db.commit()
    encoded_name = quote(item.filename)
    return Response(
        content=item.file_data, media_type=item.content_type or XLSX_CONTENT_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@admin_router.post("/{application_id}/import")
def import_application(
    application_id: uuid.UUID,
    operation_id: OperationId,
    skip_duplicates: bool = False,
    allow_overflow: bool = False,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict:
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="application.import",
        target_type="application", target_id=str(application_id),
        payload={"skip_duplicates": skip_duplicates, "allow_overflow": allow_overflow},
    )
    if replay is not None:
        return replay
    item = db.scalar(select(ApplicationFile).where(ApplicationFile.id == application_id).with_for_update())
    if not item:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    event = db.get(Event, item.event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала добавлять участников нельзя")
    analysis = analyze(
        db,
        event,
        read_rows(item.filename, item.file_data, strict_application_template=True),
        serialize=True,
    )
    if analysis.errors:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_import_rows", "message": "В сохранённой заявке обнаружены ошибки",
            **analysis.response(),
        })
    if analysis.duplicates and not skip_duplicates:
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_participants",
            "message": "В заявке есть участники, которые уже находятся в системе.",
            **analysis.response(),
        })
    if analysis.overflow and not allow_overflow:
        raise HTTPException(status_code=409, detail={
            "code": "set_capacity_overflow",
            "message": "После импорта будет превышена вместимость одного или нескольких сетов.",
            "sets": analysis.overflow,
        })
    response = create_participants_from_analysis(
        db, event, analysis, application_type=ApplicationType.collective, operation_id=operation_id,
    )
    item.status = "imported"
    item.imported_at = datetime.now(timezone.utc)
    item.import_count += 1
    item.imported_by_id = admin.id
    item.import_operation_id = operation_id
    item.duplicate_rows = analysis.duplicates
    item.overflow_sets = len(analysis.overflow)
    response["application_id"] = str(item.id)
    response["status"] = "imported"
    response["import_count"] = item.import_count
    write_audit(
        db, actor=admin, action="application.reimport" if item.import_count > 1 else "application.import",
        target_type="application", target_id=str(item.id),
        new_value={"filename": item.filename, "imported": response.get("imported", 0), "import_count": item.import_count},
    )
    complete_operation(record, response)
    db.commit()
    return response


@admin_router.delete("/{application_id}")
def delete_application(
    application_id: uuid.UUID,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, str]:
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="application.delete",
        target_type="application", target_id=str(application_id), payload={},
    )
    if replay is not None:
        return replay
    item = db.get(ApplicationFile, application_id)
    if not item:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    response = {"status": "deleted", "filename": item.filename}
    complete_operation(record, response)
    db.delete(item)
    db.commit()
    return response
