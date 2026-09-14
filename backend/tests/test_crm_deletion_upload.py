import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Admin, ApplicationFile, ApplicationType, Ascent, AuditLog, Club, Event, EventStage, Participant, RolePermission, UserRole
from test_applications import application_xlsx
from test_stage4_reception_clubs import command_headers, create_participant


def prepare(festival):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.preparation
        event.qualification_started_at = None
        db.commit()


def club_payload(client, auth_headers, person):
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers).json()
    club = next(c for c in clubs if any(p["id"] == person["id"] for p in c["members"]))
    return f"/api/v1/admin/clubs/{club['id']}", {
        "expected_version": club["version"],
        "expected_versions": {p["id"]: p["version"] for p in club["members"]},
    }


@pytest.mark.parametrize("stage", [EventStage.qualification, EventStage.final, EventStage.completed])
def test_deletion_blocked_after_preparation(client, festival, auth_headers, stage):
    person = create_participant(client, festival, auth_headers, "Сохранить")
    url, payload = club_payload(client, auth_headers, person)
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = stage
        db.commit()
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=payload).status_code == 409
    assert client.request("DELETE", f"/api/v1/admin/participants/{person['id']}", headers=command_headers(auth_headers), json={"expected_version": person["version"]}).status_code == 409
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(person["id"])) is not None


def test_individual_delete_version_replay_and_audit(client, festival, auth_headers):
    person = create_participant(client, festival, auth_headers, "Удалить")
    prepare(festival)
    url = f"/api/v1/admin/participants/{person['id']}"
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json={"expected_version": person["version"] + 1}).status_code == 409
    headers = command_headers(auth_headers)
    result = client.request("DELETE", url, headers=headers, json={"expected_version": person["version"]})
    assert result.status_code == 200, result.text
    assert client.request("DELETE", url, headers=headers, json={"expected_version": person["version"]}).json() == result.json()
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(person["id"])) is None
        assert db.scalar(select(Club).where(Club.name == person["club"])) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "participant.delete")) is not None


def test_club_delete_checks_members_and_removes_both_application_types(client, festival, auth_headers):
    first = create_participant(client, festival, auth_headers, "Первый")
    url, stale = club_payload(client, auth_headers, first)
    second = create_participant(client, festival, auth_headers, "Второй")
    outsider = create_participant(client, festival, auth_headers, "Другой", club="Другой клуб")
    with SessionLocal() as db:
        db.get(Participant, uuid.UUID(second["id"])).application_type = ApplicationType.collective
        db.commit()
    prepare(festival)
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=stale).status_code == 409
    url, payload = club_payload(client, auth_headers, first)
    bad = {**payload, "expected_versions": {**payload["expected_versions"], first["id"]: 999}}
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=bad).status_code == 409
    headers = command_headers(auth_headers)
    result = client.request("DELETE", url, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["deleted_participants"] == 2
    assert client.request("DELETE", url, headers=headers, json=payload).json() == result.json()
    with SessionLocal() as db:
        assert db.get(Club, uuid.UUID(url.split("/")[-1])) is None
        assert db.get(Participant, uuid.UUID(first["id"])) is None
        assert db.get(Participant, uuid.UUID(second["id"])) is None
        assert db.get(Participant, uuid.UUID(outsider["id"])) is not None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "club.delete")) is not None


def test_delete_checks_permissions_and_remaining_results(client, festival, auth_headers):
    person = create_participant(client, festival, auth_headers, "Защищённый")
    prepare(festival)
    url, payload = club_payload(client, auth_headers, person)
    person_url = f"/api/v1/admin/participants/{person['id']}"
    with SessionLocal() as db:
        db.add(Ascent(participant_id=uuid.UUID(person["id"]), route_id=festival["route_ids"][0], is_completed=True))
        db.commit()
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=payload).status_code == 409
    assert client.request("DELETE", person_url, headers=command_headers(auth_headers), json={"expected_version": person["version"]}).status_code == 409
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = UserRole.route_judge
        db.commit()
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=payload).status_code == 403
    assert client.request("DELETE", person_url, headers=command_headers(auth_headers), json={"expected_version": person["version"]}).status_code == 403




def test_deletion_cannot_target_a_previous_competition(client, festival, auth_headers):
    person = create_participant(client, festival, auth_headers, "Прошлый")
    url, payload = club_payload(client, auth_headers, person)
    prepare(festival)
    with SessionLocal() as db:
        db.add(Event(title="Следующее соревнование", location="Скалодром", starts_on=date(2027, 10, 17), stage=EventStage.preparation))
        db.commit()
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=payload).status_code == 404
    assert client.request("DELETE", f"/api/v1/admin/participants/{person['id']}", headers=command_headers(auth_headers), json={"expected_version": person["version"]}).status_code == 404
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(person["id"])) is not None


@pytest.mark.parametrize("allowed", ["clubs.manage", "participants.manage"])
def test_club_deletion_requires_both_permissions(client, festival, auth_headers, allowed):
    person = create_participant(client, festival, auth_headers, "Защищённый")
    url, payload = club_payload(client, auth_headers, person)
    prepare(festival)
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = UserRole.reception
        db.add(RolePermission(role=UserRole.reception, permission=allowed, is_allowed=True))
        db.commit()
    assert client.request("DELETE", url, headers=command_headers(auth_headers), json=payload).status_code == 403
