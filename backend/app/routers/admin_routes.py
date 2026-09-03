import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_admin
from app.models import Admin, Ascent, Event, Participant, Route, RouteGradePoint
from app.operations import OperationId, begin_operation, complete_operation, require_version
from app.permissions import Permission, require_permission
from app.schemas import (
    RouteBulkCreate, RouteBulkPointsUpdate, RouteCreate, RouteGradePointRead, RouteGradePointsPreview,
    RouteGradePointsResponse, RouteGradePointsUpdate, RouteRead, RouteUpdate,
)
from app.services import refresh_published_route_values


router = APIRouter(prefix="/admin", tags=["admin-routes"], dependencies=[Depends(require_permission(Permission.routes_manage))])
ROUTE_GRADES = [f"{level}{suffix}" for level in (5, 6, 7, 8) for suffix in ("A", "A+", "B", "B+", "C", "C+")]


def current_event(db: Session) -> Event:
    event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
    if not event:
        raise HTTPException(status_code=404, detail="Фестиваль не найден")
    return event


def renumber_routes(db: Session, event_id: uuid.UUID) -> list[Route]:
    routes = list(db.scalars(select(Route).where(
        Route.event_id == event_id,
    ).order_by(Route.number, Route.sort_order, Route.id).with_for_update()).all())
    if not routes:
        return routes
    old_numbers = {route.id: route.number for route in routes}
    offset = max(route.number for route in routes) + len(routes) + 1
    for route in routes:
        route.number += offset
        route.sort_order += offset
    db.flush()
    for number, route in enumerate(routes, start=1):
        old_number = old_numbers[route.id]
        if route.name.strip().casefold() == f"трасса {old_number}".casefold():
            route.name = f"Трасса {number}"
        route.number = number
        route.sort_order = number
    db.flush()
    return routes


def ensure_grade_points(db: Session, event: Event, *, lock: bool = False) -> list[RouteGradePoint]:
    query = select(RouteGradePoint).where(RouteGradePoint.event_id == event.id)
    if lock:
        query = query.with_for_update()
    existing = {item.grade: item for item in db.scalars(query).all()}
    for grade in ROUTE_GRADES:
        if grade not in existing:
            item = RouteGradePoint(event_id=event.id, grade=grade, points=None)
            db.add(item)
            existing[grade] = item
    db.flush()
    return [existing[grade] for grade in ROUTE_GRADES]


def grade_points_response(db: Session, event: Event) -> RouteGradePointsResponse:
    settings = ensure_grade_points(db, event)
    route_counts = dict(db.execute(select(Route.grade, func.count()).where(
        Route.event_id == event.id, Route.grade.in_(ROUTE_GRADES),
    ).group_by(Route.grade)).all())
    return RouteGradePointsResponse(items=[RouteGradePointRead(
        grade=item.grade, points=item.points, effective_points=item.points or 0,
        expected_version=item.version, route_count=route_counts.get(item.grade, 0),
    ) for item in settings])


def changed_grade_points(settings: list[RouteGradePoint], payload: RouteGradePointsUpdate) -> dict[str, int | None]:
    if len(payload.items) != len(ROUTE_GRADES) or {item.grade for item in payload.items} != set(ROUTE_GRADES):
        raise HTTPException(status_code=422, detail="Передайте полный справочник категорий сложности")
    if len({item.grade for item in payload.items}) != len(payload.items):
        raise HTTPException(status_code=422, detail="Категория сложности указана несколько раз")
    current = {item.grade: item for item in settings}
    return {item.grade: item.points for item in payload.items if current[item.grade].points != item.points}


def grade_points_preview(db: Session, event: Event, payload: RouteGradePointsUpdate) -> RouteGradePointsPreview:
    settings = ensure_grade_points(db, event)
    changes = changed_grade_points(settings, payload)
    grades = list(changes)
    affected_routes = db.scalar(select(func.count()).select_from(Route).where(
        Route.event_id == event.id, Route.grade.in_(grades),
    )) if grades else 0
    affected_participants = db.scalar(select(func.count(func.distinct(Participant.id))).select_from(Participant).join(
        Ascent, Ascent.participant_id == Participant.id,
    ).join(Route, Route.id == Ascent.route_id).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None),
        Ascent.is_completed.is_(True), Route.grade.in_(grades),
    )) if grades else 0
    return RouteGradePointsPreview(
        changed_grades=len(grades), affected_routes=affected_routes or 0,
        affected_participants=affected_participants or 0,
    )


@router.get("/route-grade-points", response_model=RouteGradePointsResponse)
def read_route_grade_points(db: Session = Depends(get_db)) -> RouteGradePointsResponse:
    return grade_points_response(db, current_event(db))


@router.post("/route-grade-points/preview", response_model=RouteGradePointsPreview)
def preview_route_grade_points(
    payload: RouteGradePointsUpdate, db: Session = Depends(get_db),
) -> RouteGradePointsPreview:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала очки сложностей заблокированы")
    return grade_points_preview(db, event, payload)


@router.put("/route-grade-points", response_model=RouteGradePointsResponse)
def update_route_grade_points(
    payload: RouteGradePointsUpdate, operation_id: OperationId,
    db: Session = Depends(get_db), admin: Admin = Depends(get_current_admin),
) -> RouteGradePointsResponse | dict:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала очки сложностей заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.grade-points.update",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    settings = ensure_grade_points(db, event, lock=True)
    changes = changed_grade_points(settings, payload)
    payload_by_grade = {item.grade: item for item in payload.items}
    for setting in settings:
        require_version(setting, payload_by_grade[setting.grade].expected_version)
        if setting.grade in changes:
            setting.points = changes[setting.grade]
    if changes:
        for route in db.scalars(select(Route).where(
            Route.event_id == event.id, Route.grade.in_(list(changes)),
        ).with_for_update()).all():
            route.points = changes[route.grade] or 0
        db.flush()
        refresh_published_route_values(db, event.id)
    db.flush()
    response = grade_points_response(db, event).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/routes", response_model=RouteRead, status_code=201)
def create_route(
    payload: RouteCreate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> RouteRead | dict:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    db.execute(select(Event).where(Event.id == event.id).with_for_update()).scalar_one()
    route_id = uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:route:{operation_id}")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.create",
        target_type="route", target_id=str(route_id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    existing_count = len(renumber_routes(db, event.id))
    if payload.grade not in ROUTE_GRADES:
        raise HTTPException(status_code=422, detail="Неизвестная категория сложности")
    setting = next(item for item in ensure_grade_points(db, event) if item.grade == payload.grade)
    route = Route(
        id=route_id, event_id=event.id, number=existing_count + 1, sort_order=existing_count + 1,
        name=payload.name.strip(), grade=payload.grade.strip(), points=setting.points or 0, is_active=True,
    )
    db.add(route)
    db.flush()
    response = RouteRead.model_validate(route).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.post("/routes/bulk", response_model=list[RouteRead], status_code=201)
def create_routes_bulk(
    payload: RouteBulkCreate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> list[RouteRead] | dict:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    if payload.grade not in ROUTE_GRADES:
        raise HTTPException(status_code=422, detail="Неизвестная категория сложности")
    db.execute(select(Event).where(Event.id == event.id).with_for_update()).scalar_one()
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.bulk-create",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    existing_count = len(renumber_routes(db, event.id))
    setting = next(item for item in ensure_grade_points(db, event) if item.grade == payload.grade)
    routes = [Route(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"parkrock:route:{operation_id}:{index}"),
        event_id=event.id, number=existing_count + index, sort_order=existing_count + index,
        name=f"Трасса {existing_count + index}", grade=payload.grade,
        points=setting.points or 0, is_active=True,
    ) for index in range(1, payload.count + 1)]
    db.add_all(routes)
    db.flush()
    response = [RouteRead.model_validate(route).model_dump(mode="json") for route in routes]
    complete_operation(record, response)
    db.commit()
    return response


@router.patch("/routes/bulk-points")
def update_route_points_bulk(
    payload: RouteBulkPointsUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, int]:
    if payload.from_grade not in ROUTE_GRADES or payload.to_grade not in ROUTE_GRADES:
        raise HTTPException(status_code=422, detail="Неизвестная категория сложности")
    start = ROUTE_GRADES.index(payload.from_grade)
    end = ROUTE_GRADES.index(payload.to_grade)
    if start > end:
        raise HTTPException(status_code=422, detail="Начальная категория не может быть сложнее конечной")
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.bulk-points",
        target_type="event", target_id=str(event.id), payload=payload.model_dump(mode="json"),
    )
    if replay is not None:
        return replay
    grades = ROUTE_GRADES[start:end + 1]
    routes = list(db.scalars(select(Route).where(Route.event_id == event.id, Route.grade.in_(grades))).all())
    for route in routes:
        expected = payload.expected_versions.get(route.id)
        if expected is None:
            raise HTTPException(status_code=409, detail="Список трасс изменился. Обновите страницу и повторите действие")
        require_version(route, expected)
        route.points = payload.points
    for setting in ensure_grade_points(db, event, lock=True):
        if setting.grade in grades:
            setting.points = payload.points
    db.flush()
    refresh_published_route_values(db, event.id)
    response = {"updated": len(routes)}
    complete_operation(record, response)
    db.commit()
    return response


@router.patch("/routes/{route_id}", response_model=RouteRead)
def update_route(
    route_id: uuid.UUID,
    payload: RouteUpdate,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> RouteRead | dict:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Трасса не найдена")
    if db.get(Event, route.event_id).final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.update",
        target_type="route", target_id=str(route_id), payload=payload.model_dump(mode="json", exclude_unset=True),
    )
    if replay is not None:
        return replay
    require_version(route, payload.expected_version)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    for field in ("name", "grade"):
        if field in changes:
            changes[field] = changes[field].strip()
    if "grade" in changes:
        if changes["grade"] not in ROUTE_GRADES:
            raise HTTPException(status_code=422, detail="Неизвестная категория сложности")
        setting = next(item for item in ensure_grade_points(db, db.get(Event, route.event_id)) if item.grade == changes["grade"])
        changes["points"] = setting.points or 0
    for field, value in changes.items():
        setattr(route, field, value)
    db.flush()
    refresh_published_route_values(db, route.event_id)
    db.flush()
    response = RouteRead.model_validate(route).model_dump(mode="json")
    complete_operation(record, response)
    db.commit()
    return response


@router.delete("/routes")
def delete_all_routes(
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, int]:
    event = current_event(db)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    db.execute(select(Event).where(Event.id == event.id).with_for_update()).scalar_one()
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.delete-all",
        target_type="event", target_id=str(event.id), payload={},
    )
    if replay is not None:
        return replay
    routes = list(db.scalars(select(Route).where(Route.event_id == event.id).with_for_update()).all())
    route_ids = [route.id for route in routes]
    if route_ids:
        completed_count = db.scalar(select(func.count()).select_from(Ascent).where(
            Ascent.route_id.in_(route_ids), Ascent.is_completed.is_(True),
        )) or 0
        if completed_count:
            raise HTTPException(status_code=409, detail="Нельзя удалить все трассы: по одной или нескольким трассам уже сохранены прохождения")
        assigned_count = db.scalar(select(func.count()).select_from(Admin).where(
            Admin.assigned_route_id.in_(route_ids),
        )) or 0
        if assigned_count:
            raise HTTPException(status_code=409, detail="Сначала снимите трассы с назначенных судей")
    for route in routes:
        db.delete(route)
    db.flush()
    response = {"deleted": len(routes)}
    complete_operation(record, response)
    db.commit()
    return response


@router.delete("/routes/{route_id}")
def delete_route(
    route_id: uuid.UUID,
    expected_version: int,
    operation_id: OperationId,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> dict[str, str | int]:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Трасса не найдена")
    event = db.get(Event, route.event_id)
    if event.final_started_at:
        raise HTTPException(status_code=409, detail="После запуска финала трассы квалификации заблокированы")
    record, replay = begin_operation(
        db, operation_id=operation_id, admin_id=admin.id, action="route.delete",
        target_type="route", target_id=str(route_id),
        payload={"expected_version": expected_version},
    )
    if replay is not None:
        return replay
    require_version(route, expected_version)
    completed_count = db.scalar(select(func.count()).select_from(Ascent).where(
        Ascent.route_id == route.id, Ascent.is_completed.is_(True),
    )) or 0
    if completed_count:
        raise HTTPException(status_code=409, detail="Нельзя удалить трассу, по которой уже сохранены прохождения")
    assigned_count = db.scalar(select(func.count()).select_from(Admin).where(
        Admin.assigned_route_id == route.id,
    )) or 0
    if assigned_count:
        raise HTTPException(status_code=409, detail="Сначала снимите эту трассу с назначенных судей")
    response = {"status": "deleted", "number": route.number}
    db.delete(route)
    db.flush()
    renumber_routes(db, event.id)
    complete_operation(record, response)
    db.commit()
    return response
