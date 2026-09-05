import json
from datetime import date

from sqlalchemy.engine import make_url

from app import backup_service
from app.config import settings
from app.db import SessionLocal
from app.models import Admin, CompetitionSet, Participant, Sex, UserRole


def test_backups_are_available_only_to_administrator(client, festival, auth_headers, monkeypatch):
    monkeypatch.setattr(backup_service, "list_backups", lambda db: {"items": [], "current": {"counts": {}}, "directory": "backups"})
    response = client.get("/api/v1/admin/backups", headers=auth_headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        admin = db.get(Admin, festival["admin_id"])
        admin.role = UserRole.secretary
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/admin/backups", headers=auth_headers)
    assert response.status_code == 403


def test_backup_delete_requires_exact_confirmation(client, auth_headers):
    response = client.request(
        "DELETE", "/api/v1/admin/backups/example.dump", headers=auth_headers,
        json={"confirmation": "удалить"},
    )
    assert response.status_code == 422
    assert "УДАЛИТЬ" in response.json()["detail"]


def test_backup_filename_cannot_escape_directory():
    try:
        backup_service.resolve_backup("../database.dump")
    except backup_service.BackupError as error:
        assert "имя" in str(error).lower()
    else:
        raise AssertionError("Path traversal must be rejected")


def test_stage_checkpoint_is_selected_by_snapshot_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIRECTORY", tmp_path)
    event_id = "festival-1"

    def create(name, created_at, source_stage, kind="stage-transition"):
        archive = tmp_path / f"{name}.dump"
        archive.write_bytes(b"archive")
        archive.with_suffix(".json").write_text(json.dumps({
            "created_at": created_at,
            "context": {"event_id": event_id, "kind": kind},
            "summary": {"event": {"stage": source_stage}},
        }), encoding="utf-8")
        return archive

    expected = create("qualification-checkpoint", "2026-09-05T10:00:00+00:00", "qualification")
    create("newer-final-checkpoint", "2026-09-05T11:00:00+00:00", "final")
    create("newer-pre-rollback", "2026-09-05T12:00:00+00:00", "qualification", "pre-rollback")

    assert backup_service.find_stage_checkpoint(event_id, "qualification") == expected


def test_set_state_and_participant_assignments_survive_restore(festival):
    with SessionLocal() as db:
        participant = Participant(
            event_id=festival["event_id"], club_id=festival["club_id"],
            set_id=festival["first_set_id"], start_number=101,
            surname="Сохранов", name="Сет", birth_date=date(1994, 1, 1),
            sex=Sex.male, sport_rank="Без разряда", club="Тестовый клуб",
            representative="",
        )
        db.add(participant)
        db.commit()
        participant_id = participant.id

    database = str(make_url(settings.database_url).database)
    state = backup_service._capture_set_state(database)

    with SessionLocal() as db:
        first_set = db.get(CompetitionSet, festival["first_set_id"])
        first_set.name = "Старое имя из копии"
        first_set.scheduled_on = None
        db.get(Participant, participant_id).set_id = festival["second_set_id"]
        obsolete_set = CompetitionSet(
            event_id=festival["event_id"], name="Сет из старой копии",
            scheduled_on=None, time_label="00:00-01:00", capacity=10,
        )
        db.add(obsolete_set)
        db.commit()
        obsolete_set_id = obsolete_set.id

    backup_service._apply_set_state(database, state)

    with SessionLocal() as db:
        first_set = db.get(CompetitionSet, festival["first_set_id"])
        assert first_set.name == "Сет 1"
        assert db.get(Participant, participant_id).set_id == festival["first_set_id"]
        assert db.get(CompetitionSet, obsolete_set_id) is None
