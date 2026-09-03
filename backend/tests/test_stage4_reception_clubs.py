import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Club, Participant


def command_headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def create_participant(client, festival, auth_headers, surname: str, merch_size="M", club="Клуб Этапа 4", representative="Анна Представитель"):
    response = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": surname, "name": "Тест",
            "birth_date": "1994-05-06", "sex": "male", "sport_rank": "Без разряда",
            "club": club, "representative": representative, "merch_size": merch_size,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_individual_reception_statuses_can_be_set_and_reverted(client, festival, auth_headers):
    participant = create_participant(client, festival, auth_headers, "Индивидуальный")
    updated = client.patch(
        f"/api/v1/admin/participants/{participant['id']}/reception",
        headers=command_headers(auth_headers),
        json={"expected_version": participant["version"], "checked_in": True, "is_paid": True, "merch_issued": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["checked_in_at"] is not None
    assert updated.json()["is_paid"] is True
    assert updated.json()["merch_issued"] is True

    reverted = client.patch(
        f"/api/v1/admin/participants/{participant['id']}/reception",
        headers=command_headers(auth_headers),
        json={"expected_version": updated.json()["version"], "checked_in": False, "is_paid": False, "merch_issued": False},
    )
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["checked_in_at"] is None
    assert reverted.json()["is_paid"] is False
    assert reverted.json()["merch_issued"] is False


def test_club_bulk_action_is_atomic_and_audited(client, festival, auth_headers):
    first = create_participant(client, festival, auth_headers, "Первый")
    second = create_participant(client, festival, auth_headers, "Второй", merch_size=None)
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers)
    assert clubs.status_code == 200, clubs.text
    club = clubs.json()[0]
    assert club["representative"] == "Анна Представитель"
    assert [item["start_number"] for item in club["members"]] == [first["start_number"], second["start_number"]]

    invalid = client.post(
        f"/api/v1/admin/clubs/{club['id']}/bulk", headers=command_headers(auth_headers),
        json={
            "participant_ids": [first["id"], second["id"]],
            "expected_versions": {first["id"]: first["version"], second["id"]: second["version"] + 1},
            "is_paid": True,
        },
    )
    assert invalid.status_code == 409
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(first["id"])).is_paid is False
        assert db.get(Participant, uuid.UUID(second["id"])).is_paid is False

    successful = client.post(
        f"/api/v1/admin/clubs/{club['id']}/bulk", headers=command_headers(auth_headers),
        json={
            "participant_ids": [first["id"], second["id"]],
            "expected_versions": {first["id"]: first["version"], second["id"]: second["version"]},
            "is_paid": True,
        },
    )
    assert successful.status_code == 200, successful.text
    assert successful.json()["updated"] == 2
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(first["id"])).is_paid is True
        assert db.get(Participant, uuid.UUID(second["id"])).is_paid is True
        assert db.scalar(select(AuditLog).where(AuditLog.action == "club.bulk-reception")) is not None


def test_club_edit_updates_directory_and_all_members(client, festival, auth_headers):
    participant = create_participant(client, festival, auth_headers, "Редактируемый")
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers).json()
    club = next(item for item in clubs if item["id"] == participant["club_id"])
    response = client.patch(
        f"/api/v1/admin/clubs/{club['id']}", headers=command_headers(auth_headers),
        json={"name": "Новое название", "representative": "Новый Представитель", "expected_version": club["version"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_participants"] == 1
    with SessionLocal() as db:
        updated = db.get(Participant, uuid.UUID(participant["id"]))
        assert updated.club == "Новое название"
        assert updated.representative == "Новый Представитель"
        assert db.scalar(select(AuditLog).where(AuditLog.action == "club.update")) is not None


def test_duplicate_clubs_can_be_confirmed_and_merged(client, festival, auth_headers):
    first = create_participant(client, festival, auth_headers, "Первый клуб", club="Одинаковый", representative="Первый Представитель")
    second = create_participant(client, festival, auth_headers, "Второй клуб", club="Одинаковый", representative="Общий Представитель")
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers).json()
    source = next(item for item in clubs if item["id"] == first["club_id"])

    conflict = client.patch(
        f"/api/v1/admin/clubs/{source['id']}", headers=command_headers(auth_headers),
        json={"name": "Одинаковый", "representative": "Общий Представитель", "expected_version": source["version"]},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "duplicate_club"
    assert conflict.json()["detail"]["target_club"]["id"] == second["club_id"]

    merged = client.patch(
        f"/api/v1/admin/clubs/{source['id']}", headers=command_headers(auth_headers),
        json={
            "name": "Одинаковый", "representative": "Общий Представитель",
            "expected_version": source["version"], "merge_duplicate": True,
        },
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["merged"] is True
    assert merged.json()["id"] == second["club_id"]

    remaining = [item for item in client.get("/api/v1/admin/clubs", headers=auth_headers).json() if item["name"] == "Одинаковый"]
    assert len(remaining) == 1
    assert remaining[0]["representative"] == "Общий Представитель"
    assert remaining[0]["participant_count"] == 2
    with SessionLocal() as db:
        assert db.get(Club, uuid.UUID(source["id"])) is None
        moved = db.get(Participant, uuid.UUID(first["id"]))
        assert str(moved.club_id) == second["club_id"]
        assert moved.representative == "Общий Представитель"
        assert db.scalar(select(AuditLog).where(AuditLog.action == "club.merge")) is not None
