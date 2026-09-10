import uuid

import pytest
from sqlalchemy import select

from app import backup_service
from app.db import SessionLocal
from app.models import Admin, AuditLog, Event, EventStage, Participant, RolePermission, UserRole
from test_stage4_reception_clubs import command_headers, create_participant


def edit_payload(person):
    return {key: person[key] for key in ("surname", "name", "patronymic", "birth_year", "sex", "sport_rank", "club", "representative")} | {"expected_version": person["version"]}


def test_edit_is_versioned_and_only_allowed_during_preparation(client, festival, auth_headers):
    person = create_participant(client, festival, auth_headers, "Ошибка")
    payload = edit_payload(person) | {"surname": "Исправлено", "birth_year": 1992, "sport_rank": "КМС", "club": "Новый клуб", "representative": "Новый представитель"}
    url = f"/api/v1/admin/participants/{person['id']}"
    for stage in (EventStage.qualification, EventStage.final, EventStage.completed):
        with SessionLocal() as db:
            db.get(Event, festival["event_id"]).stage = stage
            db.commit()
        response = client.patch(url, headers=command_headers(auth_headers), json=payload)
        assert response.status_code == 409, response.text
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = EventStage.preparation
        db.commit()
    headers = command_headers(auth_headers)
    result = client.patch(url, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["surname"] == "Исправлено"
    assert result.json()["birth_year"] == 1992
    assert result.json()["birth_date"] == "1992-05-06"
    assert result.json()["club"] == "Новый клуб"
    assert result.json()["representative"] == "Новый представитель"
    assert result.json()["start_number"] == person["start_number"]
    assert result.json()["set_id"] == person["set_id"]
    assert client.patch(url, headers=headers, json=payload).json() == result.json()
    assert client.patch(url, headers=command_headers(auth_headers), json=payload).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "participant.update")) is not None


def test_edit_checks_duplicate_identity_age_and_permission(client, festival, auth_headers):
    first = create_participant(client, festival, auth_headers, "Первый")
    second = create_participant(client, festival, auth_headers, "Второй")
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = EventStage.preparation
        db.commit()
    url = f"/api/v1/admin/participants/{second['id']}"
    assert client.patch(url, headers=command_headers(auth_headers), json=edit_payload(second) | {"surname": first["surname"]}).status_code == 409
    assert client.patch(url, headers=command_headers(auth_headers), json=edit_payload(second) | {"birth_year": 2100}).status_code == 422
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = UserRole.reception
        db.add(RolePermission(role=UserRole.reception, permission="participants.edit", is_allowed=False))
        db.commit()
    assert client.patch(url, headers=command_headers(auth_headers), json=edit_payload(second)).status_code == 403


@pytest.mark.parametrize("role", [UserRole.secretary, UserRole.reception, UserRole.route_judge])
def test_admin_can_delegate_backups_reset_merge_and_revoke(client, festival, auth_headers, monkeypatch, role):
    monkeypatch.setattr(backup_service, "list_backups", lambda db: {"items": [], "current": {}, "directory": "backups"})
    rights = ["dashboard.view", "participants.view", "backups.manage", "competition.reset", "clubs.merge", "demo.manage", "exports.create"]
    response = client.put(f"/api/v1/admin/roles/{role.value}/permissions", headers=command_headers(auth_headers), json={"permissions":rights})
    assert response.status_code == 200, response.text
    assert set(response.json()["permissions"]) == set(rights)
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = role
        db.commit()
    assert client.get("/api/v1/admin/backups", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/admin/competition/reset-status", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/admin/exports/catalog", headers=auth_headers).status_code == 200
    assert "clubs.merge" in client.get("/api/v1/auth/me", headers=auth_headers).json()["permissions"]
    with SessionLocal() as db:
        for row in db.scalars(select(RolePermission).where(RolePermission.role == role)).all():
            row.is_allowed = False
        db.commit()
    assert client.get("/api/v1/admin/backups", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/competition/reset-status", headers=auth_headers).status_code == 403
