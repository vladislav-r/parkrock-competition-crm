import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import backup_service
from app.db import SessionLocal
from app.models import Admin, Ascent, AuditLog, Event, EventStage, Participant, RolePermission, UserRole
from test_stage4_reception_clubs import command_headers, create_participant
from test_participant_edit_delegated_rights import edit_payload

REAL_CREATE_BACKUP = backup_service.create_backup


@pytest.fixture
def merge_people(client, festival, auth_headers, monkeypatch):
    first = create_participant(client, festival, auth_headers, "Дубль", club="Скала", representative="Анна")
    second = create_participant(client, festival, auth_headers, "Верный", club="Горы", representative="Иван")
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = EventStage.preparation
        person = db.get(Participant, uuid.UUID(second["id"]))
        person.surname = first["surname"]
        person.birth_year = 1995
        person.birth_date = person.birth_date.replace(year=1995)
        person.set_id = festival["second_set_id"]
        person.is_paid = True
        person.checked_in_at = datetime.now(timezone.utc)
        person.sport_rank = "КМС"
        db.commit()
    people = client.get("/api/v1/admin/participants", headers=auth_headers).json()
    first, second = [next(p for p in people if p["id"] == old["id"]) for old in (first, second)]
    calls = []
    def backup(db, **kwargs):
        with SessionLocal() as before:
            assert len(before.scalars(select(Participant)).all()) == 2
        calls.append(kwargs)
        return {"filename": "test-participant-merge.dump"}
    monkeypatch.setattr(backup_service, "create_backup", backup)
    payload = edit_payload(first) | {
        "birth_year": second["birth_year"], "target_participant_id": second["id"], "target_expected_version": second["version"],
        "primary_participant_id": first["id"], "club_participant_id": first["id"], "representative_participant_id": second["id"],
        "rank_participant_id": second["id"], "arrival_participant_id": second["id"], "payment_participant_id": second["id"],
    }
    return first, second, payload, calls


@pytest.mark.parametrize("keep_source", [True, False])
def test_merge_choices_duplicate_details_replay_and_audit(client, festival, auth_headers, merge_people, keep_source):
    first, second, payload, backups = merge_people
    collision = client.patch(f"/api/v1/admin/participants/{first['id']}", headers=command_headers(auth_headers), json=edit_payload(first) | {"birth_year": 1995})
    assert collision.status_code == 409
    assert collision.json()["detail"]["code"] == "duplicate_participant"
    assert collision.json()["detail"]["participants"][0]["id"] == second["id"]
    primary, removed = (first, second) if keep_source else (second, first)
    payload["primary_participant_id"] = primary["id"]
    headers = command_headers(auth_headers)
    url = f"/api/v1/admin/participants/{first['id']}/merge"
    result = client.post(url, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    person = result.json()["participant"]
    assert (person["id"], person["set_id"], person["start_number"]) == (primary["id"], primary["set_id"], primary["start_number"])
    assert (person["birth_year"], person["club"], person["representative"], person["sport_rank"]) == (1995, "Скала", "Иван", "КМС")
    assert person["is_paid"] and person["checked_in_at"]
    assert result.json()["removed_participant_id"] == removed["id"]
    assert client.post(url, headers=headers, json=payload).json() == result.json()
    assert len(backups) == 1
    with SessionLocal() as db:
        assert db.get(Participant, uuid.UUID(removed["id"])) is None
        assert len(db.scalars(select(Participant)).all()) == 1
        assert db.scalar(select(AuditLog).where(AuditLog.action == "participant.merge")) is not None
    assert len(client.get("/api/v1/admin/participants", headers=auth_headers).json()) == 1


@pytest.mark.parametrize("case,status", [("stale_source",409), ("stale_target",409), ("invalid_choice",422), ("same_record",422), ("identity",409), ("stage",409), ("results",409), ("backup",503), ("permission",403)])
def test_merge_rejects_without_changes(client, festival, auth_headers, merge_people, monkeypatch, case, status):
    first, second, payload, backups = merge_people
    if case == "stale_source": payload["expected_version"] += 1
    if case == "stale_target": payload["target_expected_version"] += 1
    if case == "invalid_choice": payload["club_participant_id"] = str(uuid.uuid4())
    if case == "same_record": payload["target_participant_id"] = first["id"]
    if case == "identity": payload["birth_year"] = 1996
    with SessionLocal() as db:
        if case == "stage": db.get(Event, festival["event_id"]).stage = EventStage.qualification
        if case == "results": db.add(Ascent(participant_id=uuid.UUID(first["id"]), route_id=festival["route_ids"][0], is_completed=True))
        if case == "permission":
            db.get(Admin, festival["admin_id"]).role = UserRole.secretary
            db.add(RolePermission(role=UserRole.secretary, permission="participants.edit", is_allowed=True))
            db.add(RolePermission(role=UserRole.secretary, permission="participants.merge", is_allowed=False))
        db.commit()
    if case == "backup":
        def failed_backup(*args, **kwargs): raise backup_service.BackupError("test failure")
        monkeypatch.setattr(backup_service, "create_backup", failed_backup)
    result = client.post(f"/api/v1/admin/participants/{first['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert result.status_code == status, result.text
    assert not backups
    with SessionLocal() as db:
        assert len(db.scalars(select(Participant)).all()) == 2
        assert db.get(Participant, uuid.UUID(first["id"])).birth_year == first["birth_year"]


def test_merge_permission_can_be_delegated(client, festival, auth_headers, merge_people):
    first, _, payload, _ = merge_people
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = UserRole.reception
        db.add_all([RolePermission(role=UserRole.reception, permission=p, is_allowed=True) for p in ("participants.edit", "participants.merge")])
        db.commit()
    result = client.post(f"/api/v1/admin/participants/{first['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert result.status_code == 200, result.text


def test_merge_verified_backup_restores_both_originals(client, auth_headers, merge_people, monkeypatch, tmp_path):
    first, second, payload, _ = merge_people
    monkeypatch.setattr(backup_service, "BACKUP_DIRECTORY", tmp_path)
    monkeypatch.setattr(backup_service, "create_backup", REAL_CREATE_BACKUP)
    result = client.post(f"/api/v1/admin/participants/{first['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert result.status_code == 200, result.text
    path = tmp_path / result.json()["backup_filename"]
    database = f"climbhub_verify_{uuid.uuid4().hex[:12]}"
    try:
        assert backup_service._read_metadata(path)["verified_at"]
        backup_service._create_database(database)
        backup_service._restore_archive(path, database)
        with backup_service._psycopg_connection(database) as connection:
            rows = connection.execute("SELECT birth_year, club, representative FROM participants ORDER BY birth_year").fetchall()
            assert rows == [(1994, "Скала", "Анна"), (1995, "Горы", "Иван")]
    finally:
        backup_service._drop_database(database)
        backup_service.delete_backup(path)
