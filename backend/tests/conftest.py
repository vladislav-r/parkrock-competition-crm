from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import SessionLocal, engine
from app.main import app
from app.models import Admin, AgeGroup, Club, CompetitionSet, Event, EventStage, Route, Sex
from app.security import hash_password


APP_TABLES = (
    "judge_result_conflicts",
    "audit_logs",
    "applications",
    "role_permissions",
    "operation_records",
    "final_route_attempts",
    "final_category_results",
    "final_category_routes",
    "final_routes",
    "qualification_result_snapshots",
    "qualification_category_snapshots",
    "published_results",
    "ascents",
    "participants",
    "clubs",
    "route_grade_points",
    "routes",
    "competition_sets",
    "age_groups",
    "events",
    "admins",
)


@pytest.fixture(autouse=True)
def clean_test_database():
    database_name = make_url(str(engine.url)).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError(f"Тесты запрещено запускать в базе {database_name!r}")
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {', '.join(APP_TABLES)} CASCADE"))
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {', '.join(APP_TABLES)} CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def festival():
    db = SessionLocal()
    try:
        admin = Admin(
            email="admin@test.local",
            full_name="Тестовый администратор",
            password_hash=hash_password("test-password"),
            is_active=True,
        )
        event = Event(
            title="Тестовый фестиваль",
            location="Тестовый скалодром",
            starts_on=date(2026, 10, 17),
            is_public=True,
            stage=EventStage.qualification,
            qualification_started_at=datetime.now(timezone.utc),
        )
        db.add_all([admin, event])
        db.flush()
        club = Club(event_id=event.id, name="Тестовый клуб", normalized_name="тестовый клуб", representative="")
        db.add(club)
        db.add_all([
            AgeGroup(event_id=event.id, name="Мужчины", sex=Sex.male, min_age=18, max_age=99, sort_order=1),
            AgeGroup(event_id=event.id, name="Женщины", sex=Sex.female, min_age=18, max_age=99, sort_order=2),
        ])
        first_set = CompetitionSet(event_id=event.id, name="Сет 1", time_label="09:00-12:00", capacity=20)
        second_set = CompetitionSet(event_id=event.id, name="Сет 2", time_label="13:00-16:00", capacity=20)
        routes = [
            Route(event_id=event.id, number=1, name="Трасса 1", grade="5B", points=100, sort_order=1, is_active=True),
            Route(event_id=event.id, number=2, name="Трасса 2", grade="6A", points=200, sort_order=2, is_active=True),
        ]
        db.add_all([first_set, second_set, *routes])
        db.commit()
        return {
            "admin_id": admin.id,
            "event_id": event.id,
            "club_id": club.id,
            "first_set_id": first_set.id,
            "second_set_id": second_set.id,
            "route_ids": [route.id for route in routes],
        }
    finally:
        db.close()


@pytest.fixture
def auth_headers(client, festival):
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "admin@test.local", "password": "test-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
