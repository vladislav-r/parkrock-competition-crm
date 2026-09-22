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


def test_duplicate_clubs_can_be_confirmed_and_merged(client, festival, auth_headers, monkeypatch):
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

    legacy = client.patch(
        f"/api/v1/admin/clubs/{source['id']}", headers=command_headers(auth_headers),
        json={
            "name": "Одинаковый", "representative": "Общий Представитель",
            "expected_version": source["version"], "merge_duplicate": True,
        },
    )
    assert legacy.status_code == 409
    from app import backup_service
    monkeypatch.setattr(backup_service, "create_backup", lambda *args, **kwargs: {"filename": "test-merge.dump"})
    target = next(item for item in clubs if item["id"] == second["club_id"])
    merged = client.post(
        f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers),
        json={"target_club_id": target["id"], "expected_version": source["version"],
              "target_expected_version": target["version"], "name_club_id": target["id"],
              "representative_club_id": target["id"], "source_member_ids": [first["id"]], "target_member_ids": [second["id"]]},
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


def test_unpaid_arrival_requires_explicit_confirmation(client, festival, auth_headers):
    from test_current_workflows import add_participant
    for i, endpoint in enumerate(["check-in", "reception"]):
        person_id = add_participant(event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=501+i)
        url = f"/api/v1/admin/participants/{person_id}/{endpoint}"
        method = client.post if endpoint == "check-in" else client.patch
        payload = {"expected_version": 1, **({"checked_in": True} if endpoint == "reception" else {})}
        for extra in [{}, {"allow_unpaid": False}]:
            response = method(url, headers=command_headers(auth_headers), json={**payload, **extra})
            assert response.status_code == 409, response.text
        assert method(url, headers=command_headers(auth_headers), json={**payload, "allow_unpaid": "true"}).status_code == 422
        with SessionLocal() as db:
            assert db.get(Participant, person_id).checked_in_at is None
        headers = command_headers(auth_headers)
        response = method(url, headers=headers, json={**payload, "allow_unpaid": True})
        assert response.status_code == 200, response.text
        assert response.json()["checked_in_at"] is not None
        assert response.json()["is_paid"] is False
        assert method(url, headers=headers, json={**payload, "allow_unpaid": True}).json() == response.json()
        with SessionLocal() as db:
            person = db.get(Participant, person_id)
            person.checked_in_at = None
            person.is_paid = True
            db.commit()
            payload["expected_version"] = person.version
        assert method(url, headers=command_headers(auth_headers), json=payload).status_code == 200


def test_unpaid_bulk_arrival_is_atomic(client, festival, auth_headers):
    from test_current_workflows import add_participant
    ids = [add_participant(event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=601+i) for i in range(2)]
    with SessionLocal() as db:
        db.get(Participant, ids[0]).is_paid = True
        db.commit()
        payload = {"participant_ids": [str(pid) for pid in ids], "expected_versions": {str(pid): db.get(Participant, pid).version for pid in ids}, "checked_in": True}
    url = f"/api/v1/admin/clubs/{festival['club_id']}/bulk"
    response = client.post(url, headers=command_headers(auth_headers), json=payload)
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert all(db.get(Participant, pid).checked_in_at is None for pid in ids)
    headers = command_headers(auth_headers)
    payload["allow_unpaid"] = True
    response = client.post(url, headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 2
    assert client.post(url, headers=headers, json=payload).json() == response.json()
    with SessionLocal() as db:
        assert all(db.get(Participant, pid).checked_in_at is not None for pid in ids)
        assert db.get(Participant, ids[1]).is_paid is False
