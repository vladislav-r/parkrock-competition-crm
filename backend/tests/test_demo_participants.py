import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Admin, Ascent, Event, EventStage, FinalCategoryResult, FinalRouteAttempt, Participant, UserRole


def headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def test_demo_seed_requires_empty_database_and_clear_supports_set_or_all(client, festival, auth_headers):
    seeded = client.post("/api/v1/admin/demo/participants", headers=headers(auth_headers))
    assert seeded.status_code == 201, seeded.text
    assert seeded.json()["created"] == 40

    first_set = client.get(
        f"/api/v1/admin/participants?set_id={festival['first_set_id']}", headers=auth_headers,
    )
    assert first_set.status_code == 200
    assert len(first_set.json()) == 20
    assert {group: sum(item["group_name"] == group for item in first_set.json()) for group in {"Мужчины", "Женщины"}} == {
        "Мужчины": 10, "Женщины": 10,
    }
    refused = client.post("/api/v1/admin/demo/participants", headers=headers(auth_headers))
    assert refused.status_code == 409

    cleared_set = client.delete(
        f"/api/v1/admin/demo/participants?set_id={festival['first_set_id']}", headers=headers(auth_headers),
    )
    assert cleared_set.status_code == 200
    assert cleared_set.json()["deleted"] == 20
    cleared_all = client.delete("/api/v1/admin/demo/participants", headers=headers(auth_headers))
    assert cleared_all.status_code == 200
    assert cleared_all.json()["deleted"] == 20
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 0


def test_demo_data_actions_are_administrator_only(client, festival, auth_headers):
    with SessionLocal() as db:
        admin = db.get(Admin, festival["admin_id"])
        admin.role = UserRole.secretary
        db.commit()
    denied = client.post("/api/v1/admin/demo/participants", headers=headers(auth_headers))
    assert denied.status_code == 403


def test_demo_results_fill_qualification_and_final_separately(client, festival, auth_headers):
    seeded = client.post("/api/v1/admin/demo/participants", headers=headers(auth_headers))
    assert seeded.status_code == 201, seeded.text

    qualification = client.post("/api/v1/admin/demo/qualification-results", headers=headers(auth_headers))
    assert qualification.status_code == 200, qualification.text
    assert qualification.json()["updated_participants"] == 40
    assert qualification.json()["completed_ascents"] > 0
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Ascent).where(Ascent.is_completed.is_(True))) > 0

    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    for category in status["categories"]:
        confirmed = client.post(
            f"/api/v1/admin/final/categories/{category['id']}/confirm", headers=headers(auth_headers),
            json={"expected_version": category["expected_version"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        status = confirmed.json()
    started = client.post(
        "/api/v1/admin/final/start", headers=headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert started.status_code == 200, started.text

    final = client.post("/api/v1/admin/demo/final-results", headers=headers(auth_headers))
    assert final.status_code == 200, final.text
    assert final.json()["updated_categories"] == 2
    assert final.json()["updated_finalists"] > 0
    with SessionLocal() as db:
        assert db.get(Event, festival["event_id"]).stage == EventStage.final
        assert db.scalar(select(func.count()).select_from(FinalCategoryResult)) == final.json()["updated_finalists"]
        assert db.scalar(select(func.count()).select_from(FinalRouteAttempt)) == final.json()["updated_finalists"] * 4
