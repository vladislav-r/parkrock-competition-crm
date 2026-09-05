from datetime import date

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Admin, AgeGroup, ApplicationFile, Ascent, AuditLog, Club, CompetitionSet, Event,
    Participant, Route,
)


def add_participant_with_result(festival) -> None:
    db = SessionLocal()
    try:
        participant = Participant(
            event_id=festival["event_id"], club_id=festival["club_id"], set_id=festival["first_set_id"],
            start_number=101, surname="Иванов", name="Иван", birth_date=date(2000, 1, 1),
            sex="male", club="Тестовый клуб",
        )
        db.add(participant)
        db.flush()
        db.add(Ascent(participant_id=participant.id, route_id=festival["route_ids"][0], is_completed=True))
        db.commit()
    finally:
        db.close()


def test_reset_requires_explicit_confirmation(client, festival, auth_headers):
    response = client.post(
        "/api/v1/admin/competition/reset",
        headers=auth_headers,
        json={"target": "applications", "confirmation": "да"},
    )
    assert response.status_code == 422


def test_participant_reset_preserves_configuration(client, festival, auth_headers):
    add_participant_with_result(festival)

    response = client.post(
        "/api/v1/admin/competition/reset",
        headers=auth_headers,
        json={"target": "participants", "confirmation": "СБРОСИТЬ"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["safety_backup"] == "test-pre-reset-participants.dump"

    db = SessionLocal()
    try:
        event = db.get(Event, festival["event_id"])
        assert event.stage.value == "preparation"
        assert event.qualification_started_at is None
        assert db.scalar(select(func.count(Participant.id))) == 0
        assert db.scalar(select(func.count(Ascent.id))) == 0
        assert db.scalar(select(func.count(Club.id))) == 1
        assert db.scalar(select(func.count(CompetitionSet.id))) == 2
        assert db.scalar(select(func.count(Route.id))) == 2
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "competition.reset")) == 1
    finally:
        db.close()


def test_factory_reset_creates_zero_snapshot_and_keeps_staff(client, festival, auth_headers):
    add_participant_with_result(festival)

    response = client.post(
        "/api/v1/admin/competition/reset",
        headers=auth_headers,
        json={"target": "all", "confirmation": "СБРОСИТЬ"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["zero_backup"] == "test-factory-zero-all.dump"

    db = SessionLocal()
    try:
        event = db.get(Event, festival["event_id"])
        assert event.stage.value == "preparation"
        assert event.qualification_started_at is None
        assert db.scalar(select(func.count(Admin.id))) == 1
        for model in (Participant, Club, CompetitionSet, Route, AgeGroup, ApplicationFile):
            assert db.scalar(select(func.count(model.id))) == 0
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "competition.reset")) == 1
    finally:
        db.close()
