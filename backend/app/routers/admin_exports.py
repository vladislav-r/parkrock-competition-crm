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
    CompetitionSet, UserRole, JudgeResultConflict,
)
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.protocol_exports import ProtocolRow, create_protocol_xlsx, create_table_xlsx
from app.absolute_results import absolute_rows
from app.routers import admin_final
from app.schemas import ExportSettingsRead, ExportSettingsUpdate


router = APIRouter(prefix="/admin/exports", tags=["admin-exports"], dependencies=[Depends(get_current_admin)])
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def export_staff(admin: Admin = Depends(require_permission(Permission.exports_create))) -> Admin:
    if admin.role not in {UserRole.administrator, UserRole.secretary, UserRole.chief_judge}:
        raise HTTPException(status_code=403, detail="Выгрузки доступны администратору, секретарю и главному судье")
    return admin


def export_catalog(db: Session, event: Event) -> tuple[list[dict], dict[str, tuple[list[str], list[list]]]]:
    status = admin_final.status_response(db, event)
    qualification = absolute_rows(db, event, "qualification")
    finals = absolute_rows(db, event, "final")
    people = list(db.scalars(select(Participant).where(Participant.event_id == event.id, Participant.archived_at.is_(None)).order_by(Participant.start_number)).all())
    sets = {item.id: item.name for item in db.scalars(select(CompetitionSet).where(CompetitionSet.event_id == event.id)).all()}
    by_id = {str(item.id): item for item in people}
    qual_by_id = {row["participant_id"]: row for row in qualification}
    items, datasets = [], {}
    try:
        require_complete_settings(event)
        settings_error = ""
    except HTTPException as error:
        settings_error = error.detail
    final_active = event.stage in (EventStage.final, EventStage.completed)
    conflicts = bool(db.scalar(select(JudgeResultConflict.id).where(JudgeResultConflict.event_id == event.id, JudgeResultConflict.resolution.is_(None)).limit(1)))

    def add(key, title, block, count, reason="", warnings=None):
        reason = reason or ("Нет данных для выгрузки" if not count else "") or settings_error
        items.append({"key": key, "title": title, "block": block, "row_count": count,
                      "available": not bool(reason), "reason": reason, "warnings": warnings or []})

    for category in status.categories:
        rows = [row for row in qualification if row["group_name"] == category.name]
        with_result = sum(row["has_result"] for row in rows)
        reason = "Квалификация ещё не начата" if event.stage == EventStage.preparation else ""
        if not reason and not category.confirmed and not final_active:
            reason = "Сначала подтвердите результаты категории"
        warnings = [f"Без результата квалификации: {len(rows) - with_result} участников."] if len(rows) > with_result else []
        add(f"qualification:{category.id}", category.name, "qualification", with_result, reason, warnings)
        if category.participates_in_final:
            final_rows = [row for row in finals if row["group_name"] == category.name]
            final_count = sum(row["has_result"] for row in final_rows)
            reason = "Финал ещё не начат" if not final_active else "Сначала подтвердите результаты финала категории" if not category.final_confirmed else ""
            if conflicts and not reason:
                reason = "Сначала разрешите конфликты результатов судей"
            warnings = [f"Без результата финала: {len(final_rows) - final_count} участников."] if len(final_rows) > final_count else []
            partial = sum(0 < row["final_attempt_count"] < 4 for row in final_rows)
            if partial:
                warnings.append(f"Не все четыре трассы заполнены у {partial} финалистов.")
            add(f"final:{category.id}", category.name, "final", final_count, reason, warnings)

    absolute_headers = ["Место", "Ст. №", "ФИО", "Возрастная группа", "Клуб", "Г.р.", "Разряд", "Квалификация", "Финал", "Итого"]
    for stage, title in (("qualification", "Абсолют · квалификация"), ("final", "Абсолют · финал"), ("overall", "Абсолют · соревнование")):
        rows = qualification if stage == "qualification" else finals if stage == "final" else absolute_rows(db, event, "overall")
        reason = ""
        if stage == "qualification":
            if event.stage == EventStage.preparation:
                reason = "Квалификация ещё не начата"
            elif not final_active and not status.all_categories_confirmed:
                reason = "Сначала подтвердите все категории квалификации"
        elif not final_active:
            reason = "Финал ещё не начат"
        elif stage == "overall" and event.stage != EventStage.completed:
            reason = "Итог соревнования доступен после завершения фестиваля"
        elif any(category.participates_in_final for category in status.categories) and not status.all_final_categories_confirmed:
            reason = "Сначала подтвердите все категории финала"
        if stage != "qualification" and conflicts and not reason:
            reason = "Сначала разрешите конфликты результатов судей"
        count = sum(row["has_result"] for row in rows)
        warnings = [f"Без результата: {len(rows) - count} участников; их места останутся пустыми."] if len(rows) > count else []
        if stage != "qualification":
            partial = sum(row["final_attempt_count"] < 4 for row in finals)
            if partial:
                warnings.append(f"Неполные результаты четырёх трасс у {partial} финалистов.")
        key = f"absolute:{stage}"
        add(key, title, "absolute", count, reason, warnings)
        datasets[key] = (absolute_headers, [[row["place"], row["start_number"], row["full_name"], row["group_name"], row["club"], row["birth_year"], row["sport_rank"], row["qualification_points"], row["final_points"], row["score"]] for row in rows])

    selected = {
        "participants": ("Все участники", people),
        "clubs": ("Участники по клубам", sorted(people, key=lambda person: (person.club.casefold(), person.start_number))),
        "finalists": ("Финалисты", [by_id[row["participant_id"]] for row in qualification if row["is_finalist"]]),
        "finishers": ("Финишеры с медалями", [by_id[row["participant_id"]] for row in qualification if row["medal"]]),
        "paid": ("Оплатившие участники", [person for person in people if person.is_paid]),
        "unpaid": ("Неоплатившие участники", [person for person in people if not person.is_paid]),
        "merch": ("Участники с выданным мерчем", [person for person in people if person.merch_issued]),
    }
    headers = ["Ст. №", "ФИО", "Г.р.", "Пол", "Возрастная группа", "Клуб", "Сет", "Разряд", "Оплата", "Прибытие", "Представитель", "Заявка", "Медаль", "Мерч", "Размер"]
    medals = {"gold": "Золото", "silver": "Серебро", "bronze": "Бронза"}
    for name, (title, members) in selected.items():
        key = f"other:{name}"
        reason = "Состав финалистов ещё не зафиксирован запуском финала" if name == "finalists" and not final_active else ""
        if name == "finishers" and not final_active and (event.stage == EventStage.preparation or not status.all_categories_confirmed):
            reason = "Сначала подтвердите все категории квалификации"
        warnings = ["Учёт мерча отключён; выгружаются только ранее сохранённые отметки."] if name == "merch" else []
        add(key, title, "other", len(members), reason, warnings)
        datasets[key] = (headers, [[person.start_number, f"{person.surname} {person.name} {person.patronymic}".strip(),
            person.birth_year or person.birth_date.year, "М" if person.sex.value == "male" else "Ж",
            qual_by_id[str(person.id)]["group_name"], person.club, sets.get(person.set_id, ""), person.sport_rank,
            "Оплачено" if person.is_paid else "Не оплачено", "Прибыл" if person.checked_in_at else "Не прибыл",
            person.representative, "Коллективная" if person.application_type.value == "collective" else "Индивидуальная",
            medals.get(qual_by_id[str(person.id)]["medal"], ""), "Выдан" if person.merch_issued else "Не выдан", person.merch_size or ""] for person in members])
    return items, datasets


@router.get("/catalog")
def read_export_catalog(db: Session = Depends(get_db), _: Admin = Depends(export_staff)) -> dict:
    event = current_event(db)
    items, _ = export_catalog(db, event)
    return {"stage": event.stage, "items": items}


@router.get("/files/{key}.xlsx")
def export_file(key: str, confirm_incomplete: bool = False, db: Session = Depends(get_db), admin: Admin = Depends(export_staff)) -> Response:
    event = current_event(db)
    items, datasets = export_catalog(db, event)
    item = next((item for item in items if item["key"] == key), None)
    if not item:
        raise HTTPException(status_code=404, detail="Выгрузка не найдена")
    if not item["available"]:
        raise HTTPException(status_code=409, detail=item["reason"])
    if item["warnings"] and not confirm_incomplete:
        raise HTTPException(status_code=409, detail={"code": "incomplete_export", "message": "Подтвердите выгрузку неполных данных", "warnings": item["warnings"]})
    kind, identifier = key.split(":", 1)
    if kind in ("qualification", "final"):
        function = export_qualification_protocol if kind == "qualification" else export_final_protocol
        return function(uuid.UUID(identifier), db, admin)
    headers, rows = datasets[key]
    content = create_table_xlsx(title=item["title"], headers=headers, rows=rows,
        competition_name=event.export_competition_name, location=event.export_location, dates=event.export_dates,
        official_name=event.export_official_name, official_qualification=event.export_official_qualification)
    write_audit(db, actor=admin, action="export.dataset", target_type="event", target_id=str(event.id),
                new_value={"dataset": key, "format": "xlsx", "rows": len(rows), "warnings": item["warnings"]})
    db.commit()
    return xlsx_response(content, f"{item['title'].replace(' · ', '-')}.xlsx")


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
