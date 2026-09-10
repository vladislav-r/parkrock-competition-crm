import json
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, FinalCategoryResult, FinalRouteAttempt, JudgeResultConflict, UserRole
from app.security import hash_password
from test_stage8_judge import prepare_final, judge_headers, command_headers


@pytest.mark.parametrize("choice", ["server", "judge"])
def test_delayed_judge_result_is_preserved_and_resolved_by_staff(client, festival, auth_headers, choice):
    _, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        db.add(Admin(email="offline@test.local", full_name="Судья без связи", role=UserRole.route_judge,
                     password_hash=hash_password("judge-password"), assigned_final_route_id=uuid.UUID(routes[0]["id"])))
        db.commit()
    headers = judge_headers(client, "offline@test.local")
    row = client.get("/api/v1/judge/workspace", headers=headers).json()["participants"][0]
    # The judge's queued version precedes the secretary's correction.
    with SessionLocal() as db:
        result = db.get(FinalCategoryResult, uuid.UUID(row["final_result_id"]))
        db.add(FinalRouteAttempt(event_id=festival["event_id"], final_category_result_id=result.id,
                                final_route_id=uuid.UUID(routes[0]["id"]), zone_attempt=1, top_attempt=2))
        result.version += 1
        db.commit()
    url = f"/api/v1/judge/results/{row['final_result_id']}?preserve_conflict=true"
    queued = {"expected_version": row["version"], "zone_attempt": 2, "top_attempt": 4}
    operation_headers = command_headers(headers)
    delivered = client.put(url, headers=operation_headers, json=queued)
    assert delivered.status_code == 200, delivered.text
    conflict_id = delivered.json()["submission_conflict_id"]
    assert conflict_id
    assert client.put(url, headers=operation_headers, json=queued).json() == delivered.json()
    current = client.get("/api/v1/judge/workspace", headers=headers).json()
    assert current["participants"][0]["top_attempt"] == 2
    assert current["conflicts"][0]["submitted"]["top_attempt"] == 4
    with SessionLocal() as db:
        assert len(db.scalars(select(JudgeResultConflict)).all()) == 1
    listed = client.get("/api/v1/admin/final/judge-conflicts", headers=auth_headers).json()
    assert listed[0]["current"]["top_attempt"] == 2
    resolve_url = f"/api/v1/admin/final/judge-conflicts/{conflict_id}/resolve"
    decision = {"choice": choice, "expected_version": listed[0]["expected_version"]}
    assert client.post(resolve_url, headers=command_headers(headers), json=decision).status_code == 403
    assert client.post(resolve_url, headers=command_headers(auth_headers), json={**decision, "expected_version": 999}).status_code == 409
    assert len(client.get("/api/v1/admin/final/judge-conflicts", headers=auth_headers).json()) == 1
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    blocked = client.post("/api/v1/admin/final/complete", headers=command_headers(auth_headers),
                          json={"expected_version": status["event_version"]})
    assert blocked.status_code == 409 and "конфликты" in blocked.json()["detail"]
    resolution_headers = command_headers(auth_headers)
    resolved = client.post(resolve_url, headers=resolution_headers, json=decision)
    assert resolved.status_code == 200, resolved.text
    assert client.post(resolve_url, headers=resolution_headers, json=decision).json() == resolved.json()
    assert client.post(resolve_url, headers=command_headers(auth_headers), json=decision).status_code == 409
    assert client.get("/api/v1/admin/final/judge-conflicts", headers=auth_headers).json() == []
    current = client.get("/api/v1/judge/workspace", headers=headers).json()
    assert current["participants"][0]["top_attempt"] == (4 if choice == "judge" else 2)
    assert current["conflicts"] == []
    # Even a retry after staff resolution never reapplies the old submission.
    assert client.put(url, headers=operation_headers, json=queued).status_code == 200
    with SessionLocal() as db:
        conflict = db.get(JudgeResultConflict, uuid.UUID(conflict_id))
        assert conflict.resolution == choice
        assert json.loads(conflict.details_json)["submitted"]["top_attempt"] == 4
        assert json.loads(conflict.details_json)["server_at_submission"]["top_attempt"] == 2
        assert db.scalar(select(FinalRouteAttempt)).top_attempt == (4 if choice == "judge" else 2)


def test_identical_delayed_result_is_acknowledged_without_conflict(client, festival, auth_headers):
    _, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).assigned_final_route_id = uuid.UUID(routes[0]["id"])
        db.commit()
    row = client.get("/api/v1/judge/workspace", headers=auth_headers).json()["participants"][0]
    url = f"/api/v1/judge/results/{row['final_result_id']}?preserve_conflict=true"
    for _ in range(2):
        response = client.put(url, headers=command_headers(auth_headers),
                              json={"expected_version": row["version"], "zone_attempt": None, "top_attempt": None})
        assert response.status_code == 200
        assert response.json()["submission_conflict_id"] is None
    with SessionLocal() as db:
        assert db.scalars(select(JudgeResultConflict)).all() == []
        assert len(db.scalars(select(FinalRouteAttempt)).all()) == 1
