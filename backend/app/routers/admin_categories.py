import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, AgeGroup, Event, Participant, PublishedResult, Sex
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.schemas import (
    AgeCategoriesPreview, AgeCategoriesResponse, AgeCategoriesUpdate, AgeCategoryInput, AgeCategoryRead,
)
from app.services import age_on, medal_for_points, participant_age_group, recalculate_places


router = APIRouter(prefix="/admin/categories", tags=["categories"], dependencies=[Depends(get_current_admin)])


def category_for(categories: list[AgeCategoryInput], participant: Participant, event: Event) -> AgeCategoryInput | None:
    age = age_on(participant.birth_year or participant.birth_date.year, event.starts_on)
    return next((item for item in categories if item.sex == participant.sex and item.min_age <= age
                 and (item.max_age is None or age <= item.max_age)), None)


def validate_categories(categories: list[AgeCategoryInput]) -> None:
    normalized_names = [item.name.casefold() for item in categories]
    if len(set(normalized_names)) != len(normalized_names):
        raise HTTPException(status_code=422, detail="Названия категорий не должны повторяться")
    ids = [item.id for item in categories if item.id]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="Категория указана несколько раз")
    for sex in Sex:
        rows = sorted((item for item in categories if item.sex == sex), key=lambda item: item.min_age)
        sex_label = "мужских" if sex == Sex.male else "женских"
        if not rows:
            raise HTTPException(status_code=422, detail=f"Добавьте хотя бы одну из {sex_label} категорий")
        for index, item in enumerate(rows):
            if item.max_age is not None and item.max_age < item.min_age:
                raise HTTPException(status_code=422, detail=f"В категории «{item.name}» максимальный возраст меньше минимального")
            if index:
                previous = rows[index - 1]
                if previous.max_age is None or item.min_age <= previous.max_age:
                    raise HTTPException(status_code=422, detail=f"Возрастные категории «{previous.name}» и «{item.name}» пересекаются")
                if item.min_age != previous.max_age + 1:
                    raise HTTPException(status_code=422, detail=f"Между категориями «{previous.name}» и «{item.name}» есть пропуск возрастов")
        if rows[-1].max_age is not None:
            raise HTTPException(status_code=422, detail=f"Последняя из {sex_label} категорий должна быть без верхней возрастной границы")
    for item in categories:
        ranges: list[tuple[str, int, int | None]] = []
        for medal, label in (("bronze", "бронзовой"), ("silver", "серебряной"), ("gold", "золотой")):
            minimum = getattr(item, f"{medal}_min_points")
            maximum = getattr(item, f"{medal}_max_points")
            if minimum is None and maximum is not None:
                raise HTTPException(status_code=422, detail=f"Укажите нижнюю границу {label} медали в категории «{item.name}»")
            if minimum is None:
                continue
            if maximum is not None and maximum < minimum:
                raise HTTPException(status_code=422, detail=f"Некорректный диапазон {label} медали в категории «{item.name}»")
            ranges.append((label, minimum, maximum))
        for index, (left_label, left_min, left_max) in enumerate(ranges):
            for right_label, right_min, right_max in ranges[index + 1:]:
                if left_min <= (right_max if right_max is not None else float("inf")) and right_min <= (left_max if left_max is not None else float("inf")):
                    raise HTTPException(status_code=422, detail=f"Диапазоны {left_label} и {right_label} медалей пересекаются в категории «{item.name}»")


def preview_categories(db: Session, event: Event, payload: AgeCategoriesUpdate) -> AgeCategoriesPreview:
    validate_categories(payload.categories)
    participants = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None),
    )).all())
    assignments: Counter[str] = Counter()
    transitions: Counter[tuple[str, str]] = Counter()
    unassigned = 0
    affected = 0
    for participant in participants:
        old_group = participant_age_group(db, event, participant)
        new_group = category_for(payload.categories, participant, event)
        old_name = old_group.name if old_group else "Вне категории"
        new_name = new_group.name if new_group else "Вне категории"
        assignments[new_name] += 1
        if not new_group:
            unassigned += 1
        if old_name != new_name:
            affected += 1
            transitions[(old_name, new_name)] += 1
    return AgeCategoriesPreview(
        participant_count=len(participants), affected_participants=affected,
        unassigned_participants=unassigned, assignments=dict(assignments),
        transitions=[{"from": old, "to": new, "count": count} for (old, new), count in transitions.most_common()],
    )


def read_categories(db: Session, event: Event) -> AgeCategoriesResponse:
    participants = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None),
    )).all())
    counts = Counter(group.id for participant in participants if (group := participant_age_group(db, event, participant)))
    groups = list(db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all())
    return AgeCategoriesResponse(categories=[AgeCategoryRead(
        id=item.id, expected_version=item.version, name=item.name, sex=item.sex,
        min_age=item.min_age, max_age=item.max_age, finalist_count=item.finalist_count,
        bronze_min_points=item.bronze_min_points, bronze_max_points=item.bronze_max_points,
        silver_min_points=item.silver_min_points, silver_max_points=item.silver_max_points,
        gold_min_points=item.gold_min_points, gold_max_points=item.gold_max_points,
        participant_count=counts[item.id],
    ) for item in groups])


def current_event(db: Session) -> Event:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return event


@router.get("", response_model=AgeCategoriesResponse, dependencies=[Depends(require_permission(Permission.settings_manage))])
def get_categories(db: Session = Depends(get_db)) -> AgeCategoriesResponse:
    return read_categories(db, current_event(db))


@router.post("/preview", response_model=AgeCategoriesPreview, dependencies=[Depends(require_permission(Permission.settings_manage))])
def preview(payload: AgeCategoriesUpdate, db: Session = Depends(get_db)) -> AgeCategoriesPreview:
    return preview_categories(db, current_event(db), payload)


@router.put("", dependencies=[Depends(require_permission(Permission.settings_manage))])
def save_categories(
    payload: AgeCategoriesUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> dict:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала категории и медальные диапазоны изменять нельзя")
    forecast = preview_categories(db, event, payload)
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="categories.update",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    existing = {item.id: item for item in db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id).with_for_update()).all()}
    payload_ids = {item.id for item in payload.categories if item.id}
    if any(item_id not in existing for item_id in payload_ids):
        raise HTTPException(status_code=422, detail="В конфигурации указана неизвестная категория")
    for item in payload.categories:
        if item.id:
            if item.expected_version is None:
                raise HTTPException(status_code=422, detail=f"Не указана версия категории «{item.name}»")
            require_version(existing[item.id], item.expected_version)
    for group in existing.values():
        group.name = f"__editing__{group.id}"
    db.flush()
    for item_id, group in existing.items():
        if item_id not in payload_ids:
            db.delete(group)
    fields = (
        "name", "sex", "min_age", "max_age", "finalist_count", "bronze_min_points", "bronze_max_points",
        "silver_min_points", "silver_max_points", "gold_min_points", "gold_max_points",
    )
    for order, item in enumerate(payload.categories):
        group = existing.get(item.id) if item.id else AgeGroup(event_id=event.id)
        if item.id is None:
            db.add(group)
        for field in fields:
            setattr(group, field, getattr(item, field))
        group.participates_in_final = item.finalist_count > 0
        group.sort_order = order
    db.flush()
    participants = {item.id: item for item in db.scalars(select(Participant).where(Participant.event_id == event.id)).all()}
    for result in db.scalars(select(PublishedResult).where(PublishedResult.event_id == event.id)).all():
        participant = participants.get(result.participant_id)
        group = participant_age_group(db, event, participant) if participant else None
        result.group_name = group.name if group else "Вне возрастной группы"
        result.medal = medal_for_points(group, result.points)
        result.is_finisher = result.medal is not None
    db.flush()
    recalculate_places(db, event.id)
    response = {
        "updated": len(payload.categories), "affected_participants": forecast.affected_participants,
        "unassigned_participants": forecast.unassigned_participants,
    }
    complete_operation(record, response)
    db.commit()
    return response
