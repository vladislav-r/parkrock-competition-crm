import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import String, case, cast, func, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.clubs import get_or_create_club
from app.deps import get_current_admin
from app.models import Admin, AgeGroup, ApplicationType, Ascent, CompetitionSet, Event, Participant, ParticipantSource, Route, SetStatus
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.participant_import import analyze, create_participants_from_analysis, identity, normalize, read_rows
from app.permissions import Permission, require_permission
from app.routers.public import set_read
from app.schemas import AscentRead, AscentUpdate, EventRead, GroupRead, MoveParticipant, ParticipantCreate, ParticipantRead, ParticipantResultsUpdate, PublicResultDetailsUpdate, RouteRead, SetRead, VersionedAction
from app.services import participant_age_error, participant_group

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])

@router.get("/event", response_model=EventRead, dependencies=[Depends(require_permission(Permission.dashboard_view))])
def event_dashboard(db: Session = Depends(get_db)) -> EventRead:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    sets = db.scalars(select(CompetitionSet).where(
        CompetitionSet.event_id == event.id,
    ).order_by(
        CompetitionSet.scheduled_on.asc().nulls_last(),
        CompetitionSet.time_label,
        CompetitionSet.name,
        CompetitionSet.id,
    )).all()
    routes = db.scalars(select(Route).where(Route.event_id == event.id).order_by(Route.number)).all()
    groups = db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all()
    participant_count = db.scalar(select(func.count()).select_from(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None))) or 0
    return EventRead(id=event.id, title=event.title, location=event.location, starts_on=event.starts_on,
        stage=event.stage, qualification_started_at=event.qualification_started_at,
        final_started_at=event.final_started_at, completed_at=event.completed_at,
        public_result_details_enabled=event.public_result_details_enabled,
        version=event.version,
        participant_count=participant_count,
        sets=[SetRead(**set_read(db, item).model_dump(), version=item.version) for item in sets],
        routes=[RouteRead.model_validate(r) for r in routes],
        groups=[GroupRead.model_validate(g) for g in groups])


@router.patch("/event/public-result-details", response_model=EventRead,
              dependencies=[Depends(require_permission(Permission.settings_manage))])
def update_public_result_details(
    payload: PublicResultDetailsUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> EventRead | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="event.public-result-details.update",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(event, payload.expected_version)
    event.public_result_details_enabled = payload.enabled
    event.version += 1
    db.flush()
    response = event_dashboard(db).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


def participant_read(db: Session, participant: Participant, event: Event, routes: list[Route]) -> ParticipantRead:
    ascents = {a.route_id: a.is_completed for a in db.scalars(select(Ascent).where(
        Ascent.participant_id == participant.id)).all()}
    completed = [route for route in routes if ascents.get(route.id, False)]
    return ParticipantRead(id=participant.id, club_id=participant.club_id, set_id=participant.set_id, checked_in_at=participant.checked_in_at,
        start_number=participant.start_number, surname=participant.surname, name=participant.name,
        patronymic=participant.patronymic, birth_date=participant.birth_date,
        birth_year=participant.birth_year or participant.birth_date.year, sex=participant.sex,
        sport_rank=participant.sport_rank, club=participant.club, representative=participant.representative,
        application_type=participant.application_type, merch_size=participant.merch_size,
        is_paid=participant.is_paid, merch_issued=participant.merch_issued, source=participant.source,
        import_operation_id=participant.import_operation_id,
        group_name=participant_group(db, event, participant), completed_count=len(completed),
        points=sum(r.points for r in completed),
        ascents=[AscentRead(route_id=r.id, completed=ascents.get(r.id, False)) for r in routes],
        version=participant.version)


@router.get("/participants", response_model=list[ParticipantRead], dependencies=[Depends(require_permission(Permission.participants_view))])
def participants(set_id: uuid.UUID | None = None, search: str | None = None,
                 db: Session = Depends(get_db)) -> list[ParticipantRead]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    query = select(Participant).where(Participant.event_id == event.id, Participant.archived_at.is_(None))
    normalized_search = search.strip() if search else ""
    if set_id and not normalized_search:
        query = query.where(Participant.set_id == set_id)
    if normalized_search:
        term = f"%{normalized_search}%"
        start_number_text = cast(Participant.start_number, String)
        query = query.where(
            (start_number_text.ilike(term))
            | (Participant.surname.ilike(term))
            | (Participant.name.ilike(term))
            | (Participant.club.ilike(term))
        ).order_by(
            case((start_number_text == normalized_search, 0), else_=1),
            Participant.start_number,
        )
    else:
        query = query.order_by(Participant.start_number)
    items = db.scalars(query).all()
    routes = list(db.scalars(select(Route).where(Route.event_id == event.id,
        Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    return [participant_read(db, item, event, routes) for item in items]


@router.post("/participants/import", dependencies=[Depends(require_permission(Permission.participants_import))])
async def import_participants(
    operation_id: OperationId,
    application_type: ApplicationType = ApplicationType.collective,
    preview: bool = False,
    skip_duplicates: bool = False,
    allow_overflow: bool = False,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала добавлять участников нельзя")
    content = await file.read()
    rows = read_rows(file.filename or "", content)
    analysis = analyze(db, event, rows)
    preview_response = {**analysis.response(), "application_type": application_type.value, "filename": file.filename or ""}
    if preview:
        return preview_response
    if analysis.errors:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_import_rows", "message": "Исправьте выделенные ошибки в файле", **preview_response,
        })
    if analysis.duplicates and not skip_duplicates:
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_participants", "message": "Обнаружены дубликаты. Можно загрузить только корректные строки.",
            **preview_response,
        })
    if analysis.overflow and not allow_overflow:
        raise HTTPException(status_code=409, detail={
            "code": "set_capacity_overflow", "message": "После импорта вместимость одного или нескольких сетов будет превышена.",
            "sets": analysis.overflow,
        })
    accepted_count = len([item for item in analysis.parsed_rows if not item["duplicate"]])
    if not accepted_count:
        raise HTTPException(status_code=422, detail="В файле нет корректных новых участников")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.import",
        target_type="event", target_id=str(event.id), payload={
            "application_type": application_type.value, "skip_duplicates": skip_duplicates,
            "allow_overflow": allow_overflow,
            "filename": file.filename or "",
            "content_sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    if replay is not None:
        return replay
    try:
        response = create_participants_from_analysis(
            db, event, analysis, application_type=application_type, operation_id=operation_id,
        )
        complete_operation(record, response)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return response


@router.post("/participants", response_model=ParticipantRead, status_code=201,
             dependencies=[Depends(require_permission(Permission.participants_manage))])
def create_participant(
    payload: ParticipantCreate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала добавлять участников нельзя")
    competition_set = db.get(CompetitionSet, payload.set_id)
    if not competition_set or competition_set.event_id != event.id:
        raise HTTPException(status_code=404, detail="Сет не найден")
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Сет уже завершён")
    if age_error := participant_age_error(payload.birth_date, event.starts_on):
        raise HTTPException(status_code=422, detail={"code": "invalid_age", "message": age_error, "field": "birth_date"})
    participant_id = uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:participant:{operation_id}")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.create",
        target_type="participant", target_id=str(participant_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:event_id))"), {"event_id": str(event.id)})
    existing = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None))).all())
    candidate = payload.model_dump(exclude={"set_id", "merch_size", "allow_overflow"})
    if identity(candidate) in {
        (normalize(item.surname), normalize(item.name), normalize(item.patronymic), item.birth_date) for item in existing
    }:
        db.rollback()
        raise HTTPException(status_code=409, detail="Участник с таким ФИО и датой рождения уже существует")
    assigned_count = sum(item.set_id == competition_set.id for item in existing)
    if assigned_count >= competition_set.capacity and not payload.allow_overflow:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Сет «{competition_set.name}» заполнен. Подтвердите добавление сверх вместимости")
    used = {item.start_number for item in existing}
    club_numbers = sorted(item.start_number for item in existing if normalize(item.club) == normalize(payload.club))
    candidates = [number for current in club_numbers for number in (current + 1, current - 1) if number > 0]
    start_number = next((number for number in candidates if number not in used), None)
    if start_number is None:
        start_number = 1
        while start_number in used:
            start_number += 1
    club = get_or_create_club(db, event.id, payload.club, payload.representative)
    participant = Participant(
        id=participant_id, event_id=event.id, set_id=payload.set_id, start_number=start_number,
        club_id=club.id,
        application_type=ApplicationType.individual, source=ParticipantSource.manual,
        merch_size=payload.merch_size or None, **payload.model_dump(exclude={"set_id", "merch_size", "allow_overflow"}),
        birth_year=payload.birth_date.year,
    )
    db.add(participant)
    db.flush()
    routes = list(db.scalars(select(Route).where(Route.event_id == event.id, Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    response = participant_read(db, participant, event, routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return ParticipantRead.model_validate(response)


@router.patch("/participants/{participant_id}/routes/{route_id}", response_model=ParticipantRead, dependencies=[Depends(require_permission(Permission.results_manage))])
def update_ascent(
    participant_id: uuid.UUID,
    route_id: uuid.UUID,
    payload: AscentUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    participant = db.get(Participant, participant_id)
    route = db.get(Route, route_id)
    if not participant or not route or participant.event_id != route.event_id:
        raise HTTPException(status_code=404, detail="Участник или трасса не найдены")
    participant_event = db.get(Event, participant.event_id)
    if not participant_event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Сначала начните квалификацию")
    if participant_event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала результаты квалификации заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.ascent",
        target_type="participant", target_id=str(participant_id), payload={
            **payload.model_dump(mode="json"), "route_id": str(route_id),
        },
    )
    if replay is not None:
        return replay
    require_version(participant, payload.expected_version)
    if participant.checked_in_at is None:
        raise HTTPException(status_code=409, detail="Сначала подтвердите вход участника")
    competition_set = db.get(CompetitionSet, participant.set_id)
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Сет подтвержден. Сначала откройте его для исправления")
    ascent = db.scalar(select(Ascent).where(Ascent.participant_id == participant.id, Ascent.route_id == route.id))
    if not ascent:
        ascent = Ascent(participant_id=participant.id, route_id=route.id)
        db.add(ascent)
    ascent.is_completed = payload.completed
    participant.version += 1
    db.flush()
    routes = list(db.scalars(select(Route).where(Route.event_id == participant.event_id,
        Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    response = participant_read(db, participant, db.get(Event, participant.event_id), routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.put("/participants/{participant_id}/results", response_model=ParticipantRead, dependencies=[Depends(require_permission(Permission.results_manage))])
def update_participant_results(
    participant_id: uuid.UUID,
    payload: ParticipantResultsUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Участник не найден")
    participant_event = db.get(Event, participant.event_id)
    if not participant_event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Сначала начните квалификацию")
    if participant_event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала результаты квалификации заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.results",
        target_type="participant", target_id=str(participant_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(participant, payload.expected_version)
    if participant.checked_in_at is None:
        raise HTTPException(status_code=409, detail="Сначала подтвердите вход участника")
    competition_set = db.get(CompetitionSet, participant.set_id)
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Сет подтвержден. Сначала откройте его для исправления")

    routes = list(db.scalars(select(Route).where(
        Route.event_id == participant.event_id, Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    route_ids = {route.id for route in routes}
    completed_ids = set(payload.completed_route_ids)
    unknown_ids = completed_ids - route_ids
    if unknown_ids:
        raise HTTPException(status_code=422, detail="В результатах указана неизвестная или отключенная трасса")

    ascents = {item.route_id: item for item in db.scalars(select(Ascent).where(
        Ascent.participant_id == participant.id, Ascent.route_id.in_(route_ids))).all()}
    for route in routes:
        ascent = ascents.get(route.id)
        completed = route.id in completed_ids
        if not ascent:
            ascent = Ascent(participant_id=participant.id, route_id=route.id)
            db.add(ascent)
        ascent.is_completed = completed
    participant.version += 1
    db.flush()
    response = participant_read(db, participant, db.get(Event, participant.event_id), routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.patch("/participants/{participant_id}/set", response_model=ParticipantRead, dependencies=[Depends(require_permission(Permission.participants_manage))])
def move_participant(
    participant_id: uuid.UUID,
    payload: MoveParticipant,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    participant = db.get(Participant, participant_id)
    target = db.get(CompetitionSet, payload.set_id)
    if not participant or not target or participant.event_id != target.event_id:
        raise HTTPException(status_code=404, detail="Участник или сет не найдены")
    if db.get(Event, participant.event_id).final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала распределение по сетам заблокировано")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.move",
        target_type="participant", target_id=str(participant_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(participant, payload.expected_version)
    if participant.checked_in_at is not None:
        raise HTTPException(status_code=409, detail="Нельзя переназначить сет после подтверждения входа")
    if participant.set_id == target.id:
        routes = list(db.scalars(select(Route).where(Route.event_id == participant.event_id,
            Route.is_active.is_(True)).order_by(Route.sort_order)).all())
        response = participant_read(db, participant, db.get(Event, participant.event_id), routes).model_dump(mode="json")
        complete_operation(record, response)
        db.commit()
        return response
    count = db.scalar(select(func.count()).select_from(Participant).where(
        Participant.set_id == target.id, Participant.archived_at.is_(None))) or 0
    if count >= target.capacity:
        raise HTTPException(status_code=409, detail="В выбранном сете нет свободных мест")
    if target.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Нельзя переместить участника в подтвержденный сет")
    participant.set_id = target.id
    db.flush()
    routes = list(db.scalars(select(Route).where(Route.event_id == participant.event_id,
        Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    response = participant_read(db, participant, db.get(Event, participant.event_id), routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/participants/{participant_id}/check-in", response_model=ParticipantRead, dependencies=[Depends(require_permission(Permission.participants_manage))])
def check_in_participant(
    participant_id: uuid.UUID,
    payload: VersionedAction,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    participant = db.get(Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Участник не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.check-in",
        target_type="participant", target_id=str(participant_id), payload=payload.model_dump(),
    )
    if replay is not None:
        return replay
    require_version(participant, payload.expected_version)
    competition_set = db.get(CompetitionSet, participant.set_id)
    if competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail="Сет уже завершен")
    if participant.checked_in_at is None:
        participant.checked_in_at = datetime.now(timezone.utc)
        db.flush()
    routes = list(db.scalars(select(Route).where(Route.event_id == participant.event_id,
        Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    response = participant_read(db, participant, db.get(Event, participant.event_id), routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response
