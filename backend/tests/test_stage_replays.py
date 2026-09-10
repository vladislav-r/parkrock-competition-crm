import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AgeGroup, AuditLog, Event, EventStage, OperationRecord
from app.routers import admin_final


@pytest.mark.parametrize("path,stage,target", [
    ("qualification/start", "preparation", "qualification"),
    ("qualification/cancel", "qualification", "preparation"),
    ("start", "qualification", "final"),
    ("cancel", "final", "qualification"),
    ("complete", "final", "completed"),
    ("reopen", "completed", "final"),
])
def test_stage_replay_returns_original_response_without_side_effects(
    client, festival, auth_headers, monkeypatch, path, stage, target,
):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage(stage)
        event.qualification_started_at = None if stage == "preparation" else datetime.now(timezone.utc)
        # Empty categories allow this test to focus on the transition contract.
        for group in db.scalars(select(AgeGroup)):
            group.finalist_count = 0
        db.commit()
    if path == "start":
        status = client.get("/api/v1/admin/final", headers=auth_headers).json()
        assert client.post(
            "/api/v1/admin/final/qualification/confirm-all",
            headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())},
            json={"expected_version": status["event_version"]},
        ).status_code == 200

    checkpoints = []
    monkeypatch.setattr(admin_final, "_test_database", lambda db: False)
    monkeypatch.setattr(admin_final.backup_service, "create_backup", lambda *args, **kwargs:
                        checkpoints.append(kwargs) or {"filename": "test-transition.dump"})
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    headers = {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}
    body = {"expected_version": status["event_version"]}
    url = f"/api/v1/admin/final/{path}"
    first = client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["stage"] == target

    with SessionLocal() as db:
        audit_count = db.scalar(select(func.count()).select_from(AuditLog))
        operation_count = db.scalar(select(func.count()).select_from(OperationRecord))
    for _ in range(2):
        replay = client.post(url, headers=headers, json=body)
        assert replay.status_code == 200, replay.text
        assert replay.json() == first.json()
    assert len(checkpoints) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_count
    assert client.post(url, headers=headers, json={"expected_version": body["expected_version"] + 1}).status_code == 409
    assert client.post(url, headers={**headers, "X-Operation-Id": str(uuid.uuid4())}, json=body).status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(OperationRecord)) == operation_count
        # A delayed retry must remain a replay even after a later stage change.
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.preparation
        event.version += 1
        db.commit()
    replay = client.post(url, headers=headers, json=body)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    with SessionLocal() as db:
        assert db.get(Event, festival["event_id"]).stage == EventStage.preparation
    assert len(checkpoints) == 1
