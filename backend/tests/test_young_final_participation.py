import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, AgeGroup, Event, EventStage, Participant, FinalCategoryResult, FinalRouteAttempt, QualificationResultSnapshot
from test_stage6_qualification import create_result, command_headers
from test_stage8_judge import prepare_final
from test_stage5_categories_finishers import category


def test_category_settings_keep_young_final_disabled(client, festival, auth_headers):
    payload = {"categories": [category(name, sex, minimum, maximum)
        for sex in ("male", "female")
        for name, minimum, maximum in ((f"{sex} 7-9", 7, 9), (f"{sex} 10+", 10, None))]}
    saved = client.put("/api/v1/admin/categories", headers=command_headers(auth_headers), json=payload)
    assert saved.status_code == 200, saved.text
    for _ in range(2):
        current = client.get("/api/v1/admin/categories", headers=auth_headers).json()["categories"]
        with SessionLocal() as db:
            assert all(not g.participates_in_final for g in db.scalars(select(AgeGroup).where(AgeGroup.max_age == 9)))
        fields = set(payload["categories"][0]) | {"id", "expected_version"}
        updated = {"categories": [{k: v for k, v in c.items() if k in fields} for c in current]}
        saved = client.put("/api/v1/admin/categories", headers=command_headers(auth_headers), json=updated)
        assert saved.status_code == 200, saved.text


@pytest.fixture
def young_final(client, festival, auth_headers):
    child = create_result(client, festival, auth_headers, "Ребёнок", festival["route_ids"])
    with SessionLocal() as db:
        groups = [AgeGroup(event_id=festival["event_id"], name=name, sex=sex, min_age=7, max_age=9, sort_order=order, finalist_count=10)
                  for order, (name, sex) in enumerate((("Мальчики 7-9", "male"), ("Девочки 7-9", "female")))]
        db.add_all(groups)
        person = db.get(Participant, uuid.UUID(child["id"]))
        person.birth_year, person.birth_date = 2018, date(2018, 1, 1)
        db.commit()
        assert all(not g.participates_in_final for g in groups)
    prepare_final(client, festival, auth_headers)
    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    young = next(c for c in setup["categories"] if c["name"] == "Мальчики 7-9")
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).assigned_final_route_id = uuid.UUID(setup["routes"][0]["id"])
        result = db.scalar(select(FinalCategoryResult).where(FinalCategoryResult.participant_id == uuid.UUID(child["id"])))
        result_id = str(result.id)
        db.commit()
    return child, young, result_id


def toggle(client, auth_headers, group_id, enabled, *, headers=None, version=None):
    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    return client.put(f"/api/v1/admin/final/categories/{group_id}/participation", headers=headers or command_headers(auth_headers),
        json={"expected_event_version": setup["event_version"] if version is None else version, "participates": enabled})


def test_young_final_opt_in_hides_every_surface_and_preserves_results(client, festival, auth_headers, young_final):
    child, young, result_id = young_final
    prefix = f"/api/v1/admin/final/categories/{young['id']}"
    def assert_hidden():
        setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
        item = next(c for c in setup["categories"] if c["id"] == young["id"])
        assert not item["participates"] and item["route_ids"] == [] and item["finalist_count"] == 0
        assert all(young["name"] not in r["assigned_categories"] for r in setup["routes"])
        status = client.get("/api/v1/admin/final", headers=auth_headers).json()
        assert not next(c for c in status["categories"] if c["id"] == young["id"])["participates_in_final"]
        public = client.get("/api/v1/public/results").json()
        assert young["name"] not in public["final_groups"]
        assert not next(r for r in public["results"] if r["participant_id"] == child["id"])["is_finalist"]
        assert client.get("/api/v1/public/final-results", params={"group": young["name"]}).status_code == 404
        assert client.get(prefix + "/final-results", headers=auth_headers).status_code == 409
        assert all(r["participant_id"] != child["id"] for r in client.get("/api/v1/public/absolute-results?stage=final").json()["results"])
        assert all(r["participant_id"] != child["id"] for r in client.get("/api/v1/judge/workspace", headers=auth_headers).json()["participants"])
        assert client.put(prefix + "/routes", headers=command_headers(auth_headers), json={"expected_event_version": setup["event_version"], "route_ids": [r["id"] for r in setup["routes"][:4]]}).status_code == 409
        assert client.put(f"/api/v1/judge/results/{result_id}", headers=command_headers(auth_headers), json={"expected_version":1, "zone_attempt":1, "top_attempt":1}).status_code == 409
    assert_hidden()
    old_setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    headers = command_headers(auth_headers)
    enabled = toggle(client, auth_headers, young["id"], True, headers=headers, version=old_setup["event_version"])
    assert enabled.status_code == 200, enabled.text
    assert toggle(client, auth_headers, young["id"], True, headers=headers, version=old_setup["event_version"]).json() == enabled.json()
    assert toggle(client, auth_headers, young["id"], False, version=old_setup["event_version"]).status_code == 409
    setup = enabled.json()
    routes = [r["id"] for r in setup["routes"][:4]]
    assert client.put(prefix + "/routes", headers=command_headers(auth_headers), json={"expected_event_version":setup["event_version"],"route_ids":routes}).status_code == 200
    saved = client.put(f"/api/v1/judge/results/{result_id}", headers=command_headers(auth_headers), json={"expected_version":1,"zone_attempt":1,"top_attempt":1})
    assert saved.status_code == 200, saved.text
    public = client.get("/api/v1/public/final-results", params={"group":young["name"]}).json()
    assert public["results"][0]["score"] == 25
    with SessionLocal() as db:
        snapshot = db.scalar(select(QualificationResultSnapshot).where(QualificationResultSnapshot.participant_id == uuid.UUID(child["id"])))
        frozen = (snapshot.id, snapshot.points, snapshot.place, snapshot.exit_order)
    assert toggle(client, auth_headers, young["id"], False).status_code == 200
    assert_hidden()
    with SessionLocal() as db:
        assert db.scalar(select(FinalRouteAttempt).where(FinalRouteAttempt.final_category_result_id == uuid.UUID(result_id))) is not None
        snapshot = db.get(QualificationResultSnapshot, frozen[0])
        assert (snapshot.id, snapshot.points, snapshot.place, snapshot.exit_order) == frozen
    assert toggle(client, auth_headers, young["id"], True).status_code == 200
    assert client.get("/api/v1/public/final-results", params={"group":young["name"]}).json()["results"][0]["score"] == 25


def test_young_default_does_not_block_final_confirmation(client, festival, auth_headers, young_final):
    _, young, _ = young_final
    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    for category in setup["categories"]:
        if category["participates"]:
            response = client.put(f"/api/v1/admin/final/categories/{category['id']}/routes", headers=command_headers(auth_headers),
                json={"expected_event_version":setup["event_version"],"route_ids":[r["id"] for r in setup["routes"][:4]]})
            assert response.status_code == 200, response.text
            setup = response.json()
    response = client.post("/api/v1/admin/final/final-results/confirm-all", headers=command_headers(auth_headers), json={"expected_version":setup["event_version"]})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/admin/final/complete", headers=command_headers(auth_headers), json={"expected_version":response.json()["event_version"]})
    assert response.status_code == 200, response.text
    assert toggle(client, auth_headers, young["id"], True).status_code == 409
