"""Ranges define route labels and prices; the existing scoring uses Route.points."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, Ascent, Event, Participant, Route, RouteGroup
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.routers.admin_routes import ROUTE_GRADES, current_event
from app.services import refresh_published_route_values

router = APIRouter(prefix="/admin/route-groups", tags=["admin-routes"],
                   dependencies=[Depends(require_permission(Permission.routes_manage))])


class GroupInput(BaseModel):
    from_grade: str
    to_grade: str
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    points: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_range(self):
        if self.from_grade not in ROUTE_GRADES or self.to_grade not in ROUTE_GRADES:
            raise ValueError("Выберите категории из списка")
        if ROUTE_GRADES.index(self.from_grade) > ROUTE_GRADES.index(self.to_grade):
            raise ValueError("Начальная категория не может быть сложнее конечной")
        return self


class GroupCreate(GroupInput):
    count: int = Field(default=0, ge=0, le=100)


class GroupsCreate(BaseModel):
    items: list[GroupCreate] = Field(min_length=1, max_length=24)


class GroupUpdate(GroupInput):
    expected_version: int = Field(ge=1)
    expected_route_versions: dict[uuid.UUID, int]


class GroupAddRoutes(BaseModel):
    count: int = Field(ge=1, le=100)
    expected_version: int = Field(ge=1)


def writable_event(db: Session) -> Event:
    event = current_event(db)
    db.refresh(event, with_for_update=True)
    if event.final_started_at:
        raise HTTPException(409, "После запуска финала трассы квалификации заблокированы")
    return event


def find_group(db: Session, event: Event, group_id: uuid.UUID) -> RouteGroup:
    group = db.get(RouteGroup, group_id)
    if not group or group.event_id != event.id:
        raise HTTPException(404, "Группа трасс не найдена")
    return group


def group_routes(db: Session, group: RouteGroup) -> list[Route]:
    return list(db.scalars(select(Route).where(Route.group_id == group.id).order_by(Route.number)).all())


def group_response(group: RouteGroup, routes: list[Route]) -> dict:
    return {"id": str(group.id), "from_grade": group.from_grade, "to_grade": group.to_grade,
            "grade": group.grade, "color": group.color, "points": group.points,
            "version": group.version, "route_count": len(routes),
            "route_versions": {str(route.id): route.version for route in routes}}


def check_group_versions(group: RouteGroup, routes: list[Route], payload: GroupUpdate):
    require_version(group, payload.expected_version)
    if {route.id: route.version for route in routes} != payload.expected_route_versions:
        raise HTTPException(409, "Состав или параметры трасс изменились. Обновите группу и повторите действие")


def add_routes(db: Session, event: Event, group: RouteGroup, count: int):
    last = db.scalar(select(func.max(Route.number)).where(Route.event_id == event.id)) or 0
    db.add_all([Route(event_id=event.id, group_id=group.id, number=last + i, sort_order=last + i,
                      name=f"Трасса {last + i}", grade=group.grade, points=group.points, is_active=True)
                for i in range(1, count + 1)])
    db.flush()


@router.get("")
def read_groups(db: Session = Depends(get_db)):
    event = current_event(db)
    groups = db.scalars(select(RouteGroup).where(RouteGroup.event_id == event.id)).all()
    routes = db.scalars(select(Route).where(Route.event_id == event.id).order_by(Route.number)).all()
    by_group: dict[uuid.UUID | None, list[Route]] = {}
    for route in routes:
        by_group.setdefault(route.group_id, []).append(route)
    groups.sort(key=lambda group: (ROUTE_GRADES.index(group.from_grade) if group.from_grade in ROUTE_GRADES else 99,
                                   group.to_grade, str(group.id)))
    return [group_response(group, by_group.get(group.id, [])) for group in groups]


@router.post("", status_code=201)
def create_groups(payload: GroupsCreate, operation_id: OperationId, db: Session = Depends(get_db),
                  admin: Admin = Depends(get_current_admin)):
    event = writable_event(db)
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=admin.id,
        action="route-groups.create", target_type="event", target_id=str(event.id), payload=payload.model_dump(mode="json"))
    if replay is not None:
        return replay
    response = []
    for item in payload.items:
        group = RouteGroup(event_id=event.id, **item.model_dump(exclude={"count"}))
        db.add(group)
        db.flush()
        add_routes(db, event, group, item.count)
        response.append(group_response(group, group_routes(db, group)))
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/{group_id}/preview")
def preview_group(group_id: uuid.UUID, payload: GroupUpdate, db: Session = Depends(get_db)):
    event = writable_event(db)
    group = find_group(db, event, group_id)
    routes = group_routes(db, group)
    check_group_versions(group, routes, payload)
    affected = db.scalar(select(func.count(func.distinct(Participant.id))).select_from(Participant)
        .join(Ascent, Ascent.participant_id == Participant.id).join(Route, Route.id == Ascent.route_id)
        .where(Route.group_id == group.id, Ascent.is_completed.is_(True), Participant.archived_at.is_(None))) or 0
    return {"affected_routes": len(routes), "affected_participants": affected,
            "points_changed": payload.points != group.points}


@router.put("/{group_id}")
def update_group(group_id: uuid.UUID, payload: GroupUpdate, operation_id: OperationId,
                 db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    event = writable_event(db)
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=admin.id,
        action="route-group.update", target_type="route_group", target_id=str(group_id), payload=payload.model_dump(mode="json"))
    if replay is not None:
        return replay
    group = find_group(db, event, group_id)
    routes = group_routes(db, group)
    check_group_versions(group, routes, payload)
    values_changed = (group.from_grade, group.to_grade, group.points) != (payload.from_grade, payload.to_grade, payload.points)
    for field, value in payload.model_dump(exclude={"expected_version", "expected_route_versions"}).items():
        setattr(group, field, value)
    for route in routes:
        route.grade, route.points = group.grade, group.points
    db.flush()
    if values_changed and routes:
        refresh_published_route_values(db, event.id)
    response = group_response(group, routes)
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/{group_id}/routes", status_code=201)
def create_group_routes(group_id: uuid.UUID, payload: GroupAddRoutes, operation_id: OperationId,
                        db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    event = writable_event(db)
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=admin.id,
        action="route-group.add-routes", target_type="route_group", target_id=str(group_id), payload=payload.model_dump(mode="json"))
    if replay is not None:
        return replay
    group = find_group(db, event, group_id)
    require_version(group, payload.expected_version)
    add_routes(db, event, group, payload.count)
    response = group_response(group, group_routes(db, group))
    complete_operation(record, response)
    db.commit()
    return response


@router.delete("/{group_id}")
def delete_group(group_id: uuid.UUID, expected_version: int, operation_id: OperationId,
                 db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin)):
    event = writable_event(db)
    record, replay = begin_operation(db, operation_id=operation_id, admin_id=admin.id,
        action="route-group.delete", target_type="route_group", target_id=str(group_id), payload={"expected_version": expected_version})
    if replay is not None:
        return replay
    group = find_group(db, event, group_id)
    require_version(group, expected_version)
    if group_routes(db, group):
        raise HTTPException(409, "Можно удалить только пустую группу. Сначала перенесите или удалите её трассы")
    db.delete(group)
    response = {"status": "deleted"}
    complete_operation(record, response)
    db.commit()
    return response
