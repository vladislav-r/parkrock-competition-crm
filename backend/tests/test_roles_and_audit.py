import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.db import SessionLocal
from app.models import AuditLog, Participant, Sex


def operation_headers(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "X-Operation-Id": str(uuid.uuid4())}


def create_user(client, auth_headers, *, email="reception@example.com", role="reception", route_id=None):
    return client.post(
        "/api/v1/admin/users",
        headers=operation_headers(auth_headers),
        json={
            "email": email, "full_name": "Тестовый сотрудник",
            "password": "safe-password", "role": role,
            "assigned_route_id": str(route_id) if route_id else None,
        },
    )


def login_headers(client, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login", data={"username": email, "password": "safe-password"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_admin_profile_and_standard_role_matrix(client, festival, auth_headers):
    profile = client.get("/api/v1/auth/me", headers=auth_headers)
    assert profile.status_code == 200
    assert profile.json()["role"] == "administrator"
    assert "users.manage" in profile.json()["permissions"]

    matrix = client.get("/api/v1/admin/roles", headers=auth_headers)
    assert matrix.status_code == 200
    roles = {item["role"]: set(item["permissions"]) for item in matrix.json()["roles"]}
    assert set(roles) == {"reception", "secretary", "chief_judge", "administrator", "route_judge"}
    assert "participants.manage" in roles["reception"]
    assert "routes.manage" not in roles["reception"]
    assert "judge.results" in roles["route_judge"]


def test_backend_permissions_and_denial_are_audited(client, festival, auth_headers):
    created = create_user(client, auth_headers)
    assert created.status_code == 201, created.text
    reception_headers = login_headers(client, "reception@example.com")

    assert client.get("/api/v1/admin/participants", headers=reception_headers).status_code == 200
    forbidden = client.post(
        "/api/v1/admin/routes", headers=operation_headers(reception_headers),
        json={"name": "Запрещенная трасса", "grade": "6A", "points": 100},
    )
    assert forbidden.status_code == 403

    audit = client.get(
        "/api/v1/admin/audit?action=authorization.denied", headers=auth_headers,
    )
    assert audit.status_code == 200
    assert audit.json()["total"] == 1
    assert audit.json()["items"][0]["actor_email"] == "reception@example.com"
    assert audit.json()["items"][0]["target_id"] == "routes.manage"


def test_route_judge_assignment_and_last_admin_protection(client, festival, auth_headers):
    missing_route = create_user(client, auth_headers, email="judge@example.com", role="route_judge")
    assert missing_route.status_code == 422

    created = create_user(
        client, auth_headers, email="judge@example.com", role="route_judge",
        route_id=festival["route_ids"][0],
    )
    assert created.status_code == 201, created.text
    assert created.json()["assigned_route_id"] == str(festival["route_ids"][0])

    protected = client.patch(
        f"/api/v1/admin/users/{festival['admin_id']}", headers=operation_headers(auth_headers),
        json={"expected_version": 1, "is_active": False},
    )
    assert protected.status_code == 409


def test_audit_log_is_append_only_and_records_auth_errors(client, festival, auth_headers):
    denied = client.post(
        "/api/v1/auth/login", data={"username": "admin@test.local", "password": "wrong-password"},
    )
    assert denied.status_code == 401
    audit = client.get("/api/v1/admin/audit?action=auth.login&result=denied", headers=auth_headers)
    assert audit.status_code == 200
    assert audit.json()["total"] == 1

    db = SessionLocal()
    try:
        entry = db.scalar(select(AuditLog).where(AuditLog.result == "denied"))
        with pytest.raises(DBAPIError):
            db.execute(text("UPDATE audit_logs SET result = 'changed' WHERE id = :id"), {"id": entry.id})
            db.commit()
        db.rollback()
    finally:
        db.close()


def test_user_creation_trims_fields_and_validation_error_is_explained(client, festival, auth_headers):
    created = client.post(
        "/api/v1/admin/users", headers=operation_headers(auth_headers),
        json={
            "email": "  secretary@example.com  ", "full_name": "  Секретарь фестиваля  ",
            "password": "safe-password", "role": "secretary", "assigned_route_id": None,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["email"] == "secretary@example.com"
    assert created.json()["full_name"] == "Секретарь фестиваля"
    assert created.json()["role"] == "secretary"

    chief_judge = create_user(client, auth_headers, email="mainjudge@parkrock.test", role="chief_judge")
    assert chief_judge.status_code == 201, chief_judge.text
    assert chief_judge.json()["email"] == "mainjudge@parkrock.test"
    assert chief_judge.json()["role"] == "chief_judge"

    invalid = create_user(client, auth_headers, email="judge-two@example.com", role="route_judge")
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "Для судьи необходимо назначить трассу"

    failed = client.get("/api/v1/admin/audit?action=request.failed", headers=auth_headers)
    assert failed.status_code == 200
    row = failed.json()["items"][0]
    assert row["target_label"] == "Создание пользователя"
    assert "назначить трассу" in row["details"]


def test_audit_participant_target_uses_start_number_and_name(client, festival, auth_headers):
    db = SessionLocal()
    try:
        participant = Participant(
            event_id=festival["event_id"], club_id=festival["club_id"], set_id=festival["first_set_id"], start_number=117,
            surname="Лебедева", name="Алиса", patronymic="Александровна",
            birth_date=date(2010, 4, 18), sex=Sex.female, club="Вертикаль",
        )
        db.add(participant)
        db.flush()
        db.add(AuditLog(
            actor_id=festival["admin_id"], actor_email="admin@test.local", actor_role="administrator",
            action="participant.results", target_type="participant", target_id=str(participant.id),
            result="success",
        ))
        db.commit()
    finally:
        db.close()

    audit = client.get("/api/v1/admin/audit?action=participant.results", headers=auth_headers)
    assert audit.status_code == 200
    row = audit.json()["items"][0]
    assert row["actor_name"] == "Тестовый администратор"
    assert row["target_label"] == "Участник №117"
    assert row["details"] == "Лебедева Алиса Александровна"
