import json
import random
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.clubs import get_or_create_club
from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, AgeGroup, ApplicationFile, ApplicationType, Ascent, AuditLog, CompetitionSet, Event, EventStage, FinalCategoryResult, FinalCategoryRoute, FinalRoute, FinalRouteAttempt, Participant, ParticipantSource, QualificationCategorySnapshot, RolePermission, Route, SetStatus, Sex, UserRole
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import PERMISSION_LABELS, Permission, effective_permissions, require_permission
from app.schemas import (
    AuditRead, AuditResponse, FinalRouteRead, RolePermissionRead, RolePermissionsResponse,
    RolePermissionUpdate, UserCreate, UserRead, UserUpdate,
)
from app.security import hash_password


router = APIRouter(prefix="/admin", tags=["admin-users"])

ROLE_LABELS = {
    UserRole.reception.value: "Ресепшен", UserRole.secretary.value: "Секретарь",
    UserRole.chief_judge.value: "Главный судья", UserRole.administrator.value: "Администратор",
    UserRole.route_judge.value: "Судья на трассе",
}
API_ACTIONS = {
    ("POST", "/api/v1/admin/users"): "Создание пользователя",
    ("POST", "/api/v1/admin/participants/import"): "Импорт участников",
    ("POST", "/api/v1/admin/participants"): "Ручное добавление участника",
    ("DELETE", "/api/v1/admin/demo/participants"): "Очистка участников",
    ("POST", "/api/v1/admin/demo/participants"): "Заполнение демо-участниками",
    ("POST", "/api/v1/admin/demo/qualification-results"): "Заполнение демо-результатов квалификации",
    ("POST", "/api/v1/admin/demo/final-results"): "Заполнение демо-результатов финала",
}

DEMO_SURNAMES = (
    "Волков", "Соколов", "Морозов", "Лебедев", "Орлов", "Крылов", "Белов", "Виноградов", "Громов", "Зайцев",
    "Комаров", "Ларионов", "Мельников", "Никитин", "Осипов", "Романов", "Савельев", "Титов", "Фролов", "Шаров",
)
DEMO_MALE_NAMES = ("Алексей", "Борис", "Вадим", "Глеб", "Денис", "Егор", "Иван", "Кирилл", "Лев", "Максим", "Никита", "Олег", "Павел", "Роман", "Семён", "Тимофей", "Фёдор", "Юрий", "Ярослав", "Антон")
DEMO_FEMALE_NAMES = ("Алина", "Вера", "Галина", "Дарья", "Елена", "Жанна", "Ирина", "Кира", "Лидия", "Марина", "Надежда", "Ольга", "Полина", "Раиса", "Светлана", "Тамара", "Ульяна", "Юлия", "Яна", "Анна")
DEMO_CLUBS = ("Высота", "Онсайт", "Вертикаль", "Скала", "Гранит", "Эверест")


def api_action_label(method: str, path: str) -> str:
    exact = API_ACTIONS.get((method, path))
    if exact:
        return exact
    if path.startswith("/api/v1/admin/users"):
        return "Изменение пользователя" if method in {"PATCH", "PUT", "DELETE"} else "Работа с пользователями"
    if path.startswith("/api/v1/admin/participants"):
        return "Изменение данных участника"
    if path.startswith("/api/v1/admin/routes"):
        return "Изменение трассы"
    if path.startswith("/api/v1/admin/sets"):
        return "Изменение сета"
    if path.startswith("/api/v1/admin/roles"):
        return "Изменение прав роли"
    if path.startswith("/api/v1/admin/backups"):
        return "Операция с резервной копией"
    return "Неуспешная операция"


def json_value(value: str | None) -> object | None:
    return json.loads(value) if value else None


def entity_by_id(db: Session, model, target_id: str):
    try:
        return db.get(model, uuid.UUID(target_id))
    except ValueError:
        return None


def audit_presentation(db: Session, item: AuditLog, old_value: object, new_value: object) -> tuple[str, str]:
    payload = new_value if isinstance(new_value, dict) else old_value if isinstance(old_value, dict) else {}
    if item.target_type == "participant":
        participant = entity_by_id(db, Participant, item.target_id)
        number = participant.start_number if participant else payload.get("start_number")
        parts = [
            participant.surname if participant else payload.get("surname"),
            participant.name if participant else payload.get("name"),
            participant.patronymic if participant else payload.get("patronymic"),
        ]
        full_name = " ".join(str(part) for part in parts if part)
        return f"Участник №{number}" if number else "Участник", full_name
    if item.target_type == "application":
        application = entity_by_id(db, ApplicationFile, item.target_id)
        filename = application.filename if application else payload.get("filename")
        return "Заявка", str(filename or "Файл заявки")
    if item.target_type == "user":
        user = entity_by_id(db, Admin, item.target_id)
        name = user.full_name if user else payload.get("full_name")
        email = user.email if user else payload.get("email")
        return str(name or "Пользователь"), str(email or "")
    if item.target_type == "route":
        route = entity_by_id(db, Route, item.target_id)
        number = route.number if route else payload.get("number")
        name = route.name if route else payload.get("name")
        return f"Трасса №{number}" if number else "Трасса", str(name or "")
    if item.target_type == "set":
        competition_set = entity_by_id(db, CompetitionSet, item.target_id)
        return (competition_set.name if competition_set else str(payload.get("name") or "Сет")), ""
    if item.target_type == "age_group":
        group = entity_by_id(db, AgeGroup, item.target_id)
        return (group.name if group else str(payload.get("name") or "Возрастная категория")), ""
    if item.target_type == "event":
        event = entity_by_id(db, Event, item.target_id)
        if item.action == "demo.qualification_results":
            return (event.title if event else "Фестиваль"), f"Квалификационные результаты: {payload.get('updated_participants', 0)} участников"
        if item.action == "demo.final_results":
            return (event.title if event else "Фестиваль"), f"Финальные результаты: {payload.get('updated_finalists', 0)} финалистов"
        return (event.title if event else "Фестиваль"), ""
    if item.target_type == "role":
        return f"Роль «{ROLE_LABELS.get(item.target_id, item.target_id)}»", ""
    if item.target_type == "permission":
        permission = next((label for key, label in PERMISSION_LABELS.items() if key.value == item.target_id), item.target_id)
        return f"Право «{permission}»", ""
    if item.target_type == "api":
        method = str(payload.get("method", ""))
        label = api_action_label(method, item.target_id)
        status_code = payload.get("status")
        fallback = {
            405: "Действие недоступно для этого адреса",
            409: "Данные изменились или операция конфликтует с текущим состоянием",
            422: "Проверьте заполнение обязательных полей",
        }.get(status_code, "Операция не выполнена")
        detail = payload.get("detail") or fallback
        return label, f"{detail} (код {status_code})" if status_code else str(detail)
    if item.target_type == "session":
        return "Сеанс пользователя", item.target_id
    if item.target_type == "backup":
        return "Резервная копия", item.target_id
    return "Изменённые данные", ""


def user_read(user: Admin) -> UserRead:
    return UserRead.model_validate(user)


def ensure_user_final_routes(db: Session, event: Event) -> list[FinalRoute]:
    routes = list(db.scalars(select(FinalRoute).where(
        FinalRoute.event_id == event.id,
    ).order_by(FinalRoute.number)).all())
    if not routes:
        db.add_all([FinalRoute(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:final-route:{event.id}:{number}"),
            event_id=event.id, number=number, name=f"Финал {number}",
        ) for number in range(1, 9)])
        db.flush()
        routes = list(db.scalars(select(FinalRoute).where(
            FinalRoute.event_id == event.id,
        ).order_by(FinalRoute.number)).all())
    return routes


def validate_final_route_assignment(
    db: Session, role: UserRole, route_id: uuid.UUID | None, legacy_route_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    if role != UserRole.route_judge:
        return None
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=422, detail="Фестиваль не найден")
    routes = ensure_user_final_routes(db, event)
    if route_id is None and legacy_route_id is not None:
        legacy_route = db.get(Route, legacy_route_id)
        if legacy_route and legacy_route.event_id == event.id:
            route_id = next((item.id for item in routes if item.number == legacy_route.number), None)
    if route_id is None:
        raise HTTPException(status_code=422, detail="Для судьи необходимо назначить трассу")
    route = db.get(FinalRoute, route_id)
    if not event or not route or route.event_id != event.id or route.number < 1 or route.number > 8:
        raise HTTPException(status_code=422, detail="Судье можно назначить только трассу 1–8")
    return route.id


def require_administrator(admin: Admin = Depends(get_current_admin), db: Session = Depends(get_db)) -> Admin:
    if admin.role != UserRole.administrator:
        write_audit(
            db, actor=admin, action="authorization.denied", target_type="permission",
            target_id="administrator.demo_data", result="denied",
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Действие доступно только администратору")
    return admin


def demo_birth_date(event: Event, group: AgeGroup, offset: int) -> date:
    upper_age = group.max_age if group.max_age is not None else group.min_age + 20
    age = group.min_age + max((upper_age - group.min_age) // 2, 0)
    month = offset % 12 + 1
    day = offset % 27 + 1
    year = event.starts_on.year - age - (1 if (month, day) > (event.starts_on.month, event.starts_on.day) else 0)
    return date(year, month, day)


@router.delete("/demo/participants")
def clear_demo_participants(
    operation_id: OperationId,
    set_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_administrator),
) -> dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    competition_set = None
    if set_id:
        competition_set = db.get(CompetitionSet, set_id)
        if not competition_set or competition_set.event_id != event.id:
            raise HTTPException(status_code=404, detail="Сет не найден")
    target_type = "set" if competition_set else "event"
    target_id = str(competition_set.id if competition_set else event.id)
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="participant.clear",
        target_type=target_type, target_id=target_id, payload={"set_id": str(set_id) if set_id else None},
    )
    if replay is not None:
        return replay
    conditions = [Participant.event_id == event.id]
    if set_id:
        conditions.append(Participant.set_id == set_id)
    deleted = db.execute(delete(Participant).where(*conditions)).rowcount or 0
    response = {"deleted": deleted, "scope": competition_set.name if competition_set else "all"}
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/demo/participants", status_code=status.HTTP_201_CREATED)
def seed_demo_participants(
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_administrator),
) -> dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    participant_count = db.scalar(select(func.count()).select_from(Participant).where(Participant.event_id == event.id)) or 0
    if participant_count:
        raise HTTPException(status_code=409, detail="Демо-данные можно добавить только при полностью пустом списке участников")
    competition_sets = list(db.scalars(select(CompetitionSet).where(CompetitionSet.event_id == event.id).order_by(CompetitionSet.name)).all())
    groups = list(db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id).order_by(AgeGroup.sort_order)).all())
    if not competition_sets or not groups:
        raise HTTPException(status_code=409, detail="Сначала создайте сеты и возрастные категории")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="participant.demo_seed",
        target_type="event", target_id=str(event.id), payload={"per_group": 20},
    )
    if replay is not None:
        return replay
    start_number = 1
    for competition_set in competition_sets:
        if competition_set.status == SetStatus.confirmed:
            competition_set.status = SetStatus.reopened
            competition_set.confirmed_at = None
    for group_index, group in enumerate(groups):
        names = DEMO_MALE_NAMES if group.sex == Sex.male else DEMO_FEMALE_NAMES
        for person_index in range(20):
            competition_set = competition_sets[person_index % len(competition_sets)]
            offset = group_index * 20 + person_index
            surname = DEMO_SURNAMES[offset % len(DEMO_SURNAMES)] + ("а" if group.sex == Sex.female else "")
            club_name = DEMO_CLUBS[(group_index + person_index) % len(DEMO_CLUBS)]
            club = get_or_create_club(db, event.id, club_name)
            db.add(Participant(
                event_id=event.id, set_id=competition_set.id, club_id=club.id, start_number=start_number,
                surname=surname, name=names[(offset // len(DEMO_SURNAMES)) % len(names)],
                patronymic="Демонстрационный", birth_date=demo_birth_date(event, group, offset),
                birth_year=demo_birth_date(event, group, offset).year, sex=group.sex,
                sport_rank="Без разряда", club=club_name,
                representative="", application_type=ApplicationType.collective if person_index < 16 else ApplicationType.individual,
                merch_size=("XS", "S", "M", "L", "XL", None)[person_index % 6],
                is_paid=False, merch_issued=False, source=ParticipantSource.manual,
            ))
            start_number += 1
    response = {"created": start_number - 1, "per_group": 20}
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/demo/qualification-results")
def seed_demo_qualification_results(
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_administrator),
) -> dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.qualification:
        raise HTTPException(status_code=409, detail="Демо-результаты квалификации можно заполнить только до запуска финала")
    if not event.qualification_started_at:
        raise HTTPException(status_code=409, detail="Сначала начните квалификацию")
    participants = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None)).order_by(Participant.start_number)).all())
    routes = list(db.scalars(select(Route).where(
        Route.event_id == event.id, Route.is_active.is_(True)).order_by(Route.sort_order)).all())
    if not participants:
        raise HTTPException(status_code=409, detail="Сначала добавьте участников")
    if not routes:
        raise HTTPException(status_code=409, detail="Сначала добавьте активные трассы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="demo.qualification_results",
        target_type="event", target_id=str(event.id), payload={"participants": len(participants), "routes": len(routes)},
    )
    if replay is not None:
        return replay
    rng = random.Random(uuid.uuid4().int)
    ascents = {(item.participant_id, item.route_id): item for item in db.scalars(select(Ascent).join(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None))).all()}
    completed_ascents = 0
    checked_in_at = datetime.now(timezone.utc)
    for participant in participants:
        participant.checked_in_at = participant.checked_in_at or checked_in_at
        completed_count = rng.choices(
            range(len(routes) + 1),
            weights=[max(1, len(routes) + 1 - abs(index - len(routes) * 0.45)) for index in range(len(routes) + 1)],
        )[0]
        completed_ids = {route.id for route in rng.sample(routes, k=min(completed_count, len(routes)))}
        for route in routes:
            ascent = ascents.get((participant.id, route.id))
            if not ascent:
                ascent = Ascent(participant_id=participant.id, route_id=route.id)
                db.add(ascent)
            ascent.is_completed = route.id in completed_ids
        participant.version += 1
        completed_ascents += len(completed_ids)
    response = {"updated_participants": len(participants), "completed_ascents": completed_ascents}
    write_audit(db, actor=actor, action="demo.qualification_results", target_type="event", target_id=str(event.id), new_value=response)
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/demo/final-results")
def seed_demo_final_results(
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_administrator),
) -> dict:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()).with_for_update())
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    if event.stage != EventStage.final:
        raise HTTPException(status_code=409, detail="Демо-результаты финала можно заполнить только во время финала")
    from app.routers.admin_final import ensure_final_routes, recalculate_final_category

    final_routes = ensure_final_routes(db, event)
    groups = list(db.scalars(select(AgeGroup).where(
        AgeGroup.event_id == event.id, AgeGroup.participates_in_final.is_(True)).order_by(AgeGroup.sort_order)).all())
    snapshots = {item.age_group_id: item for item in db.scalars(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id)).all()}
    final_results = list(db.scalars(select(FinalCategoryResult).where(
        FinalCategoryResult.event_id == event.id)).all())
    if not final_results:
        raise HTTPException(status_code=409, detail="В финале пока нет финалистов")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="demo.final_results",
        target_type="event", target_id=str(event.id), payload={"categories": len(groups)},
    )
    if replay is not None:
        return replay
    db.execute(delete(FinalRouteAttempt).where(FinalRouteAttempt.event_id == event.id))
    if groups:
        db.execute(delete(FinalCategoryRoute).where(
            FinalCategoryRoute.event_id == event.id, FinalCategoryRoute.age_group_id.in_([group.id for group in groups])))
    results_by_snapshot: dict[uuid.UUID, list[FinalCategoryResult]] = {}
    for result in final_results:
        results_by_snapshot.setdefault(result.category_snapshot_id, []).append(result)
    rng = random.Random(uuid.uuid4().int)
    updated_categories = 0
    updated_finalists = 0
    for group_index, group in enumerate(groups):
        snapshot = snapshots.get(group.id)
        if not snapshot:
            continue
        route_ids = [final_routes[(group_index * 2 + offset) % len(final_routes)].id for offset in range(4)]
        db.add_all([FinalCategoryRoute(event_id=event.id, age_group_id=group.id, final_route_id=route_id) for route_id in route_ids])
        category_results = sorted(results_by_snapshot.get(snapshot.id, []), key=lambda item: str(item.participant_id))
        for result_index, result in enumerate(category_results):
            for route_id in route_ids:
                roll = rng.random()
                top_attempt = rng.randint(1, 6) if roll < 0.22 else None
                zone_attempt = top_attempt if top_attempt is not None else (rng.randint(1, 8) if roll < 0.68 else None)
                if result_index == 0 and route_id == route_ids[0] and top_attempt is None:
                    top_attempt = zone_attempt = rng.randint(1, 3)
                db.add(FinalRouteAttempt(
                    event_id=event.id, final_category_result_id=result.id, final_route_id=route_id,
                    zone_attempt=zone_attempt, top_attempt=top_attempt,
                ))
            updated_finalists += 1
        db.flush()
        recalculate_final_category(db, snapshot.id, route_ids)
        updated_categories += 1
    event.version += 1
    response = {"updated_categories": updated_categories, "updated_finalists": updated_finalists}
    write_audit(db, actor=actor, action="demo.final_results", target_type="event", target_id=str(event.id), new_value=response)
    complete_operation(record, response)
    db.commit()
    return response


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_permission(Permission.users_manage)),
) -> list[UserRead]:
    return [user_read(item) for item in db.scalars(select(Admin).order_by(Admin.full_name, Admin.email)).all()]


@router.get("/users/final-routes", response_model=list[FinalRouteRead])
def list_user_final_routes(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_permission(Permission.users_manage)),
) -> list[FinalRouteRead]:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        return []
    routes = ensure_user_final_routes(db, event)
    return [FinalRouteRead(id=item.id, number=item.number, name=item.name) for item in routes]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_permission(Permission.users_manage)),
) -> UserRead | dict:
    email = payload.email.lower()
    user_id = uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:user:{operation_id}")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="user.create",
        target_type="user", target_id=str(user_id), payload={
            **payload.model_dump(mode="json", exclude={"password"}), "password_changed": True,
        },
    )
    if replay is not None:
        return replay
    if db.scalar(select(Admin).where(func.lower(Admin.email) == email)):
        raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже существует")
    assigned_final_route_id = validate_final_route_assignment(
        db, payload.role, payload.assigned_final_route_id, payload.assigned_route_id,
    )
    user = Admin(
        id=user_id, email=email, full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password), role=payload.role,
        assigned_route_id=payload.assigned_route_id if payload.role == UserRole.route_judge else None,
        assigned_final_route_id=assigned_final_route_id, is_active=True,
    )
    db.add(user)
    db.flush()
    response = user_read(user).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_permission(Permission.users_manage)),
) -> UserRead | dict:
    user = db.get(Admin, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="user.update",
        target_type="user", target_id=str(user_id), payload={
            **payload.model_dump(mode="json", exclude={"password"}, exclude_unset=True),
            "password_changed": payload.password is not None,
        },
    )
    if replay is not None:
        return replay
    require_version(user, payload.expected_version)
    next_role = payload.role or user.role
    next_active = payload.is_active if payload.is_active is not None else user.is_active
    if user.role == UserRole.administrator and user.is_active and (next_role != UserRole.administrator or not next_active):
        active_admins = db.scalar(select(func.count()).select_from(Admin).where(
            Admin.role == UserRole.administrator, Admin.is_active.is_(True), Admin.id != user.id,
        )) or 0
        if active_admins == 0:
            raise HTTPException(status_code=409, detail="Нельзя отключить или сменить роль последнего администратора")
    if payload.email is not None:
        email = payload.email.lower()
        duplicate = db.scalar(select(Admin).where(func.lower(Admin.email) == email, Admin.id != user.id))
        if duplicate:
            raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже существует")
        user.email = email
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    user.role = next_role
    user.is_active = next_active
    final_route_supplied = "assigned_final_route_id" in payload.model_fields_set
    legacy_route_supplied = "assigned_route_id" in payload.model_fields_set
    requested_route = payload.assigned_final_route_id if final_route_supplied else (None if legacy_route_supplied else user.assigned_final_route_id)
    requested_legacy_route = payload.assigned_route_id if legacy_route_supplied else None
    user.assigned_route_id = requested_legacy_route if next_role == UserRole.route_judge and legacy_route_supplied else (user.assigned_route_id if not final_route_supplied and next_role == UserRole.route_judge else None)
    user.assigned_final_route_id = validate_final_route_assignment(db, next_role, requested_route, requested_legacy_route)
    db.flush()
    response = user_read(user).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.get("/roles", response_model=RolePermissionsResponse)
def role_matrix(
    db: Session = Depends(get_db),
    _: Admin = Depends(require_permission(Permission.roles_manage)),
) -> RolePermissionsResponse:
    return RolePermissionsResponse(
        roles=[RolePermissionRead(
            role=role, permissions=sorted(item.value for item in effective_permissions(db, role)),
        ) for role in UserRole],
        available_permissions={item.value: PERMISSION_LABELS[item] for item in Permission},
    )


@router.put("/roles/{role}/permissions", response_model=RolePermissionRead)
def update_role_permissions(
    role: UserRole,
    payload: RolePermissionUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    actor: Admin = Depends(require_permission(Permission.roles_manage)),
) -> RolePermissionRead | dict:
    if role == UserRole.administrator:
        raise HTTPException(status_code=409, detail="Права роли администратора защищены")
    known = {item.value for item in Permission}
    requested = set(payload.permissions)
    unknown = requested - known
    if unknown:
        raise HTTPException(status_code=422, detail=f"Неизвестные разрешения: {', '.join(sorted(unknown))}")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=actor.id, action="role.permissions.update",
        target_type="role", target_id=role.value, payload={"permissions": sorted(requested)},
    )
    if replay is not None:
        return replay
    rows = {item.permission: item for item in db.scalars(select(RolePermission).where(
        RolePermission.role == role)).all()}
    for permission in Permission:
        row = rows.get(permission.value)
        if not row:
            row = RolePermission(role=role, permission=permission.value)
            db.add(row)
        row.is_allowed = permission.value in requested
    response = RolePermissionRead(role=role, permissions=sorted(requested)).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.get("/audit", response_model=AuditResponse)
def audit_log(
    action: str | None = None,
    actor: str | None = None,
    result: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Admin = Depends(require_permission(Permission.audit_view)),
) -> AuditResponse:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if actor:
        conditions.append(AuditLog.actor_email.ilike(f"%{actor.strip()}%"))
    if result:
        conditions.append(AuditLog.result == result)
    query = select(AuditLog).where(*conditions)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)).all()
    actor_names = {item.email.lower(): item.full_name for item in db.scalars(select(Admin)).all()}
    result_items = []
    for item in items:
        old_value = json_value(item.old_value_json)
        new_value = json_value(item.new_value_json)
        target_label, details = audit_presentation(db, item, old_value, new_value)
        result_items.append(AuditRead(
            id=item.id, actor_email=item.actor_email, actor_role=item.actor_role,
            actor_name=actor_names.get(item.actor_email.lower(), ""),
            action=item.action, target_type=item.target_type, target_id=item.target_id,
            target_label=target_label, details=details,
            old_value=old_value, new_value=new_value,
            result=item.result, created_at=item.created_at,
        ))
    return AuditResponse(items=result_items, total=total)
