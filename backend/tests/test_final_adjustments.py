import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Event, EventStage


def command_headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def test_qualification_must_be_started_before_results_can_change(client, festival, auth_headers):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.preparation
        event.qualification_started_at = None
        db.commit()

    participant = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Старт", "name": "Квалификации",
            "birth_date": "1998-01-01", "sex": "male", "sport_rank": "Без разряда",
            "club": "Тестовый клуб", "representative": "", "merch_size": None,
        },
    ).json()
    participant = client.post(
        f"/api/v1/admin/participants/{participant['id']}/check-in", headers=command_headers(auth_headers),
        json={"expected_version": participant["version"]},
    ).json()
    blocked = client.put(
        f"/api/v1/admin/participants/{participant['id']}/results", headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(festival["route_ids"][0])], "expected_version": participant["version"]},
    )
    assert blocked.status_code == 409
    assert "начните квалификацию" in blocked.json()["detail"]

    event = client.get("/api/v1/admin/event", headers=auth_headers).json()
    started = client.post(
        "/api/v1/admin/final/qualification/start", headers=command_headers(auth_headers),
        json={"expected_version": event["version"]},
    )
    assert started.status_code == 200, started.text
    assert started.json()["qualification_started_at"] is not None

    saved = client.put(
        f"/api/v1/admin/participants/{participant['id']}/results", headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(festival["route_ids"][0])], "expected_version": participant["version"]},
    )
    assert saved.status_code == 200, saved.text


def test_public_participant_details_are_closed_by_default_and_can_be_enabled(client, festival, auth_headers):
    participant = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Публичный", "name": "Участник",
            "birth_date": "1998-01-01", "sex": "male", "sport_rank": "Без разряда",
            "club": "Тестовый клуб", "representative": "", "merch_size": None,
        },
    ).json()
    closed = client.get(f"/api/v1/public/participants/{participant['id']}")
    assert closed.status_code == 403
    event = client.get("/api/v1/admin/event", headers=auth_headers).json()
    enabled = client.patch(
        "/api/v1/admin/event/public-result-details", headers=command_headers(auth_headers),
        json={"enabled": True, "expected_version": event["version"]},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["public_result_details_enabled"] is True
    assert client.get(f"/api/v1/public/participants/{participant['id']}").status_code == 200


def test_completed_festival_can_return_to_final(client, festival, auth_headers):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.completed
        event.completed_at = datetime.now(timezone.utc)
        db.commit()
    event = client.get("/api/v1/admin/event", headers=auth_headers).json()
    reopened = client.post(
        "/api/v1/admin/final/reopen", headers=command_headers(auth_headers),
        json={"expected_version": event["version"]},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["stage"] == "final"
    assert reopened.json()["completed_at"] is None


def test_all_qualification_confirmations_can_be_reopened(client, festival, auth_headers):
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    confirmed = client.post(
        "/api/v1/admin/final/qualification/confirm-all", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["all_categories_confirmed"] is True

    reopened = client.post(
        "/api/v1/admin/final/qualification/reopen-all", headers=command_headers(auth_headers),
        json={"expected_version": confirmed.json()["event_version"]},
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["all_categories_confirmed"] is False
    assert all(category["confirmed"] is False for category in reopened.json()["categories"])
    assert all(category["final_result_count"] == 0 for category in reopened.json()["categories"])


def test_started_qualification_can_return_to_preparation(client, festival, auth_headers):
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    cancelled = client.post(
        "/api/v1/admin/final/qualification/cancel", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["stage"] == "preparation"
    assert cancelled.json()["qualification_started_at"] is None
    assert cancelled.json()["all_categories_confirmed"] is False
