import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.clubs import normalize_club_name
from app.models import Admin, ApplicationType, Club, CompetitionSet, Event, Participant, Route, SetStatus
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.routers.admin import participant_read
from app.schemas import ClubBulkAction, ClubMemberRead, ClubRead, ClubUpdate, ParticipantRead, ParticipantReceptionUpdate


router = APIRouter(prefix="/admin", tags=["reception"], dependencies=[Depends(get_current_admin)])


def member_read(participant: Participant, set_name: str) -> ClubMemberRead:
    return ClubMemberRead(
        id=participant.id, start_number=participant.start_number,
        full_name=" ".join(filter(None, [participant.surname, participant.name, participant.patronymic])),
        set_id=participant.set_id, set_name=set_name, application_type=participant.application_type,
        checked_in=participant.checked_in_at is not None, is_paid=participant.is_paid,
        merch_size=participant.merch_size, merch_issued=participant.merch_issued,
        version=participant.version,
    )


@router.get("/clubs", response_model=list[ClubRead], dependencies=[Depends(require_permission(Permission.participants_view))])
def clubs(db: Session = Depends(get_db)) -> list[ClubRead]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    sets = {item.id: item.name for item in db.scalars(select(CompetitionSet).where(
        CompetitionSet.event_id == event.id)).all()}
    result = []
    for club in db.scalars(select(Club).where(Club.event_id == event.id).order_by(
        Club.name, Club.representative,
    )).all():
        participants = list(db.scalars(select(Participant).where(
            Participant.club_id == club.id, Participant.archived_at.is_(None),
        ).order_by(Participant.start_number)).all())
        members = [member_read(item, sets.get(item.set_id, "Сет не найден")) for item in participants]
        if not members:
            continue
        result.append(ClubRead(
            id=club.id, version=club.version, name=club.name,
            representative=club.representative or next((p.representative for p in participants if p.representative), ""),
            participant_count=len(members),
            collective_count=sum(item.application_type == ApplicationType.collective for item in participants),
            checked_in_count=sum(item.checked_in for item in members),
            paid_count=sum(item.is_paid for item in members),
            merch_issued_count=sum(item.merch_issued for item in members),
            members=members,
        ))
    return result


@router.patch("/clubs/{club_id}", dependencies=[Depends(require_permission(Permission.clubs_manage))])
def update_club(
    club_id: uuid.UUID, payload: ClubUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> dict:
    club = db.scalar(select(Club).where(Club.id == club_id).with_for_update())
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id,
        action="club.merge" if payload.merge_duplicate else "club.update",
        target_type="club", target_id=str(club.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(club, payload.expected_version)
    normalized_name = normalize_club_name(payload.name)
    normalized_representative = normalize_club_name(payload.representative)
    duplicate = db.scalar(select(Club).where(
        Club.event_id == club.event_id, Club.normalized_name == normalized_name,
        Club.normalized_representative == normalized_representative, Club.id != club.id,
    ).with_for_update())
    if duplicate and not payload.merge_duplicate:
        duplicate_participants = list(db.scalars(select(Participant.id).where(
            Participant.club_id == duplicate.id, Participant.archived_at.is_(None),
        )).all())
        raise HTTPException(status_code=409, detail={
            "code": "duplicate_club",
            "message": "Клуб с таким названием и представителем уже существует. Можно объединить заявки.",
            "target_club": {
                "id": str(duplicate.id), "name": duplicate.name,
                "representative": duplicate.representative,
                "participant_count": len(duplicate_participants),
            },
        })
    if payload.merge_duplicate and not duplicate:
        raise HTTPException(status_code=409, detail={
            "code": "merge_target_changed",
            "message": "Клуб для объединения изменился. Обновите список и повторите действие.",
        })
    participants = list(db.scalars(select(Participant).where(Participant.club_id == club.id).with_for_update()).all())
    if duplicate:
        for participant in participants:
            participant.club_record = duplicate
            participant.club = duplicate.name
            participant.representative = duplicate.representative
            participant.version += 1
        duplicate.version += 1
        db.delete(club)
        db.flush()
        response = {
            "id": str(duplicate.id), "name": duplicate.name,
            "representative": duplicate.representative, "version": duplicate.version,
            "updated_participants": len(participants), "merged": True,
        }
        complete_operation(record, response)
        db.commit()
        return response
    club.name = payload.name
    club.normalized_name = normalized_name
    club.representative = payload.representative
    club.normalized_representative = normalized_representative
    for participant in participants:
        participant.club = payload.name
        participant.representative = payload.representative
        participant.version += 1
    db.flush()
    response = {
        "id": str(club.id), "name": club.name, "representative": club.representative,
        "version": club.version, "updated_participants": len(participants), "merged": False,
    }
    complete_operation(record, response)
    db.commit()
    return response


def apply_reception_status(participant: Participant, *, checked_in: bool | None, is_paid: bool | None,
                           merch_issued: bool | None, competition_set: CompetitionSet) -> None:
    if checked_in is True and competition_set.status == SetStatus.confirmed:
        raise HTTPException(status_code=409, detail=f"Сет «{competition_set.name}» уже завершен")
    if merch_issued is True and not participant.merch_size:
        raise HTTPException(status_code=409, detail=f"Участнику №{participant.start_number} мерч не заказан")
    if checked_in is not None:
        participant.checked_in_at = datetime.now(timezone.utc) if checked_in else None
    if is_paid is not None:
        participant.is_paid = is_paid
    if merch_issued is not None:
        participant.merch_issued = merch_issued
    participant.version += 1


@router.patch(
    "/participants/{participant_id}/reception", response_model=ParticipantRead,
    dependencies=[Depends(require_permission(Permission.participants_manage))],
)
def update_participant_reception(
    participant_id: uuid.UUID, payload: ParticipantReceptionUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> ParticipantRead | dict:
    participant = db.scalar(select(Participant).where(Participant.id == participant_id).with_for_update())
    if not participant or participant.archived_at is not None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="participant.reception-update",
        target_type="participant", target_id=str(participant.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    require_version(participant, payload.expected_version)
    competition_set = db.get(CompetitionSet, participant.set_id)
    apply_reception_status(participant, checked_in=payload.checked_in, is_paid=payload.is_paid,
                           merch_issued=payload.merch_issued, competition_set=competition_set)
    db.flush()
    event = db.get(Event, participant.event_id)
    routes = list(db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    response = participant_read(db, participant, event, routes).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post(
    "/clubs/{club_id}/bulk", dependencies=[Depends(require_permission(Permission.participants_manage))],
)
def bulk_club_reception(
    club_id: uuid.UUID, payload: ClubBulkAction, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> dict:
    club = db.get(Club, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Клуб не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="club.bulk-reception",
        target_type="club", target_id=str(club.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    participants = list(db.scalars(select(Participant).where(
        Participant.id.in_(payload.participant_ids), Participant.archived_at.is_(None),
    ).order_by(Participant.start_number).with_for_update()).all())
    if len(participants) != len(payload.participant_ids) or any(item.club_id != club.id for item in participants):
        raise HTTPException(status_code=422, detail="В операции указаны участники другого клуба или удаленные записи")
    sets = {item.id: item for item in db.scalars(select(CompetitionSet).where(
        CompetitionSet.event_id == club.event_id)).all()}
    for participant in participants:
        require_version(participant, payload.expected_versions[participant.id])
        apply_reception_status(
            participant, checked_in=payload.checked_in, is_paid=payload.is_paid,
            merch_issued=payload.merch_issued, competition_set=sets[participant.set_id],
        )
    response = {
        "updated": len(participants), "participant_ids": [str(item.id) for item in participants],
        "checked_in": payload.checked_in, "is_paid": payload.is_paid, "merch_issued": payload.merch_issued,
    }
    complete_operation(record, response)
    db.commit()
    return response
