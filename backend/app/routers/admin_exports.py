import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.db import get_db
from app.deps import get_current_admin
from app.models import (
    Admin,
    AgeGroup,
    Event,
    EventStage,
    Participant,
    QualificationResultSnapshot,
)
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.protocol_exports import ProtocolRow, create_protocol_xlsx
from app.routers import admin_final
from app.schemas import ExportSettingsRead, ExportSettingsUpdate


router = APIRouter(prefix="/admin/exports", tags=["admin-exports"], dependencies=[Depends(get_current_admin)])
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def current_event(db: Session, *, lock: bool = False) -> Event:
    query = select(Event).order_by(Event.starts_on.desc())
    if lock:
        query = query.with_for_update()
    event = db.scalar(query)
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return event


def settings_response(event: Event) -> ExportSettingsRead:
    return ExportSettingsRead(
        competition_name=event.export_competition_name,
        location=event.export_location,
        dates=event.export_dates,
        official_name=event.export_official_name,
        official_qualification=event.export_official_qualification,
        event_version=event.version,
    )


def require_complete_settings(event: Event) -> None:
    fields = {
        "название соревнований": event.export_competition_name,
        "адрес": event.export_location,
        "даты": event.export_dates,
        "ФИО судьи": event.export_official_name,
        "категория судьи": event.export_official_qualification,
    }
    missing = [label for label, value in fields.items() if not value.strip()]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"Заполните настройки выгрузок: {', '.join(missing)}",
        )


def group_or_404(db: Session, group_id: uuid.UUID, event: Event) -> AgeGroup:
    group = db.get(AgeGroup, group_id)
    if not group or group.event_id != event.id:
        raise HTTPException(status_code=404, detail="Возрастная категория не найдена")
    return group


def participant_details(db: Session, participant_ids: list[uuid.UUID]) -> dict[uuid.UUID, Participant]:
    if not participant_ids:
        return {}
    return {
        participant.id: participant
        for participant in db.scalars(select(Participant).where(Participant.id.in_(participant_ids))).all()
    }


def xlsx_response(content: bytes, filename: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=content,
        media_type=XLSX_CONTENT_TYPE,
        headers={"Content-Disposition": f"attachment; filename=protocol.xlsx; filename*=UTF-8''{encoded}"},
    )


@router.get("/settings", response_model=ExportSettingsRead)
def read_export_settings(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_permission(Permission.settings_manage)),
) -> ExportSettingsRead:
    return settings_response(current_event(db))


@router.put("/settings", response_model=ExportSettingsRead)
def update_export_settings(
    payload: ExportSettingsUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_permission(Permission.settings_manage)),
) -> ExportSettingsRead | dict:
    event = current_event(db, lock=True)
    record, replay = begin_operation(
        db,
        operation_id=operation_id,
        admin_id=admin.id,
        action="export.settings.update",
        target_type="event",
        target_id=str(event.id),
        payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    previous = settings_response(event).model_dump(mode="json")
    event.export_competition_name = payload.competition_name
    event.export_location = payload.location
    event.export_dates = payload.dates
    event.export_official_name = payload.official_name
    event.export_official_qualification = payload.official_qualification
    event.version += 1
    db.flush()
    response = settings_response(event).model_dump(mode="json")
    write_audit(
        db,
        actor=admin,
        action="export.settings.update",
        target_type="event",
        target_id=str(event.id),
        old_value=previous,
        new_value=response,
    )
    complete_operation(record, response)
    db.commit()
    return response


@router.get("/qualification/{group_id}.xlsx")
def export_qualification_protocol(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_permission(Permission.exports_create)),
) -> Response:
    event = current_event(db)
    require_complete_settings(event)
    group = group_or_404(db, group_id, event)
    if event.stage == EventStage.preparation:
        raise HTTPException(status_code=409, detail="Квалификация ещё не начата")
    review = admin_final.read_category_results(group.id, db)
    if not review.confirmed:
        raise HTTPException(status_code=409, detail="Сначала подтвердите результаты возрастной категории")
    participants = participant_details(db, [item.participant_id for item in review.results])
    rows = []
    for item in review.results:
        participant = participants[item.participant_id]
        rows.append(ProtocolRow(
            place=item.place,
            full_name=f"{participant.surname} {participant.name}",
            club=item.club,
            birth_year=participant.birth_year or participant.birth_date.year,
            sport_rank=participant.sport_rank,
            completed_count=item.completed_count,
            points=item.points,
        ))
    content = create_protocol_xlsx(
        competition_name=event.export_competition_name,
        location=event.export_location,
        dates=event.export_dates,
        official_name=event.export_official_name,
        official_qualification=event.export_official_qualification,
        category_name=group.name,
        category_min_age=group.min_age,
        stage="qualification",
        rows=rows,
    )
    write_audit(
        db, actor=admin, action="export.qualification-protocol", target_type="age_group",
        target_id=str(group.id), new_value={"name": group.name, "format": "xlsx", "rows": len(rows)},
    )
    db.commit()
    return xlsx_response(content, f"протокол-квалификации-{group.name}.xlsx")


@router.get("/final/{group_id}.xlsx")
def export_final_protocol(
    group_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_permission(Permission.exports_create)),
) -> Response:
    event = current_event(db)
    require_complete_settings(event)
    group = group_or_404(db, group_id, event)
    if event.stage not in (EventStage.final, EventStage.completed):
        raise HTTPException(status_code=409, detail="Финал ещё не начат")
    category, signature = admin_final.final_category_state(db, event, group.id)
    if not category:
        raise HTTPException(status_code=404, detail="Снимок возрастной категории не найден")
    if not category.final_confirmed_at or category.final_signature != signature:
        raise HTTPException(status_code=409, detail="Сначала подтвердите результаты финала этой категории")
    setup = admin_final.final_setup_response(db, event)
    category_setup = next((item for item in setup.categories if item.id == group.id), None)
    if not category_setup or len(category_setup.route_ids) != 4:
        raise HTTPException(status_code=409, detail="Сначала назначьте категории четыре финальные трассы")
    admin_final.recalculate_final_category(db, category.id, category_setup.route_ids)
    db.flush()
    results = admin_final.final_category_results_response(db, event, group)
    qualification_rows = {
        item.participant_id: item
        for item in db.scalars(select(QualificationResultSnapshot).where(
            QualificationResultSnapshot.category_snapshot_id == category.id,
        )).all()
    }
    participants = participant_details(db, [item.participant_id for item in results.results])
    rows = []
    for item in results.results:
        participant = participants[item.participant_id]
        qualification = qualification_rows[item.participant_id]
        rows.append(ProtocolRow(
            place=item.place if item.has_result else None,
            full_name=f"{qualification.surname} {qualification.name}",
            club=qualification.club,
            birth_year=participant.birth_year or participant.birth_date.year,
            sport_rank=participant.sport_rank,
            completed_count=qualification.completed_count,
            points=qualification.points,
            top_count=item.top_count if item.has_result else None,
            zone_count=item.zone_count if item.has_result else None,
            top_attempts=item.top_attempts if item.has_result else None,
            zone_attempts=item.zone_attempts if item.has_result else None,
        ))
    content = create_protocol_xlsx(
        competition_name=event.export_competition_name,
        location=event.export_location,
        dates=event.export_dates,
        official_name=event.export_official_name,
        official_qualification=event.export_official_qualification,
        category_name=category.name,
        category_min_age=category.min_age,
        stage="final",
        rows=rows,
    )
    write_audit(
        db, actor=admin, action="export.final-protocol", target_type="age_group",
        target_id=str(group.id), new_value={"name": group.name, "format": "xlsx", "rows": len(rows)},
    )
    db.commit()
    return xlsx_response(content, f"итоговый-протокол-{group.name}.xlsx")
