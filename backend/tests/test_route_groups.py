from conftest import refresh_publication

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Ascent, Event, PublishedResult, Route, RouteGroup
from app.services import publish_set
from test_stage6_qualification import create_result


def headers(auth):
    return {**auth, "X-Operation-Id": str(uuid.uuid4())}


def create(client, auth, **values):
    response = client.post("/api/v1/admin/route-groups", headers=headers(auth), json={"items": [{
        "from_grade": "6A+", "to_grade": "6B", "color": "#00aa55", "points": 45, "count": 2, **values,
    }]})
    assert response.status_code == 201, response.text
    return response.json()[0]


def update_payload(group, **changes):
    return {key: group[key] for key in ("from_grade", "to_grade", "color", "points")} | {
        "expected_version": group["version"], "expected_route_versions": group["route_versions"], **changes,
    }


def test_ranges_score_and_recalculation_preserve_ascents(client, festival, auth_headers):
    green = create(client, auth_headers)
    blue = create(client, auth_headers, from_grade="6B+", to_grade="6C", points=140, count=1)
    ids = list(green["route_versions"])
    participant = create_result(client, festival, auth_headers, "Диапазонов", ids + list(blue["route_versions"]))
    participant_id = uuid.UUID(participant["id"])
    with SessionLocal() as db:
        publish_set(db, festival["first_set_id"])
        db.commit()
        result = db.scalar(select(PublishedResult).where(PublishedResult.participant_id == participant_id))
        assert result.points == 230
        before = {r.id: (r.number, r.group_id) for r in db.scalars(select(Route)).all()}
        ascents = [(a.id, a.route_id, a.is_completed) for a in db.scalars(select(Ascent)).all()]

    payload = update_payload(green, points=60, from_grade="6A", color="#aaff00")
    preview = client.post(f"/api/v1/admin/route-groups/{green['id']}/preview", headers=auth_headers, json=payload)
    assert preview.json() == {"affected_routes": 2, "affected_participants": 1, "points_changed": True}
    operation = headers(auth_headers)
    changed = client.put(f"/api/v1/admin/route-groups/{green['id']}", headers=operation, json=payload)
    assert changed.status_code == 200, changed.text
    assert client.put(f"/api/v1/admin/route-groups/{green['id']}", headers=operation, json=payload).json() == changed.json()
    assert client.put(f"/api/v1/admin/route-groups/{green['id']}", headers=headers(auth_headers), json=payload).status_code == 409
    with SessionLocal() as db:
        result = db.scalar(select(PublishedResult).where(PublishedResult.participant_id == participant_id))
        assert (result.points, result.completed_count) == (260, 3)
        assert "6A–6B" in result.completed_routes_json
        assert before == {r.id: (r.number, r.group_id) for r in db.scalars(select(Route)).all()}
        assert ascents == [(a.id, a.route_id, a.is_completed) for a in db.scalars(select(Ascent)).all()]
    refresh_publication()
    public = client.get("/api/v1/public/results").json()
    assert public  # Existing public route accepts the range labels.
    refresh_publication()
    absolute = client.get("/api/v1/public/absolute-results?stage=qualification")
    assert absolute.status_code == 200, absolute.text
    assert next(r for r in absolute.json()["results"] if r["participant_id"] == str(participant_id))["score"] == 260

    moved = client.patch(f"/api/v1/admin/routes/{ids[0]}", headers=headers(auth_headers), json={
        "group_id": blue["id"], "expected_version": changed.json()["route_versions"][ids[0]],
    })
    assert moved.status_code == 200, moved.text
    assert (moved.json()["grade"], moved.json()["points"]) == ("6B+–6C", 140)
    with SessionLocal() as db:
        assert db.scalar(select(PublishedResult).where(PublishedResult.participant_id == participant_id)).points == 340
    assert client.delete(f"/api/v1/admin/routes/{ids[0]}?expected_version={moved.json()['version']}", headers=headers(auth_headers)).status_code == 409


def test_batch_75_validation_repeat_and_locks(client, festival, auth_headers):
    spec = [("5A","5C",12,5),("5C+","6A",15,15),("6A+","6B",15,45),
            ("6B+","6C",15,140),("6C+","7A",9,450),("7A+","7B",6,1300),("7B+","7C",3,4000)]
    payload = {"items": [{"from_grade":a,"to_grade":b,"count":c,"points":p,"color":"#ffffff"} for a,b,c,p in spec]}
    operation = headers(auth_headers)
    response = client.post("/api/v1/admin/route-groups", headers=operation, json=payload)
    assert response.status_code == 201, response.text
    assert client.post("/api/v1/admin/route-groups", headers=operation, json=payload).json() == response.json()
    with SessionLocal() as db:
        routes = db.scalars(select(Route).where(Route.group_id.is_not(None)).order_by(Route.number)).all()
        assert len(routes) == 75
        assert [r.number for r in routes] == list(range(3,78))
        assert sum(r.points for r in routes) == 26910
        assert [db.get(Route,i).points for i in festival["route_ids"]] == [100,200]
    invalid = {"items": [payload["items"][0], {**payload["items"][1], "from_grade": "7C", "to_grade": "5A"}]}
    assert client.post("/api/v1/admin/route-groups", headers=headers(auth_headers), json=invalid).status_code == 422
    for key, value in [("points",-1),("color","red"),("count",101),("from_grade","6F")]:
        assert client.post("/api/v1/admin/route-groups", headers=headers(auth_headers), json={"items":[{**payload["items"][0],key:value}]}).status_code == 422
    group = response.json()[0]
    assert client.delete(f"/api/v1/admin/route-groups/{group['id']}?expected_version=1", headers=headers(auth_headers)).status_code == 409
    added = client.post(f"/api/v1/admin/route-groups/{group['id']}/routes", headers=headers(auth_headers), json={"count":1,"expected_version":1})
    assert added.status_code == 201
    assert client.put(f"/api/v1/admin/route-groups/{group['id']}", headers=headers(auth_headers), json=update_payload(group, points=8)).status_code == 409
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.final_started_at = datetime.now(timezone.utc)
        db.commit()
    assert client.post("/api/v1/admin/route-groups", headers=headers(auth_headers), json=payload).status_code == 409
    assert client.put(f"/api/v1/admin/route-groups/{group['id']}", headers=headers(auth_headers), json=update_payload(added.json())).status_code == 409
    assert client.post(f"/api/v1/admin/route-groups/{group['id']}/routes", headers=headers(auth_headers), json={"count":1,"expected_version":1}).status_code == 409


def test_empty_group_and_legacy_api_cannot_override_group_price(client, festival, auth_headers):
    group = create(client, auth_headers, from_grade="6A", to_grade="6A", count=1)
    route_id = next(iter(group["route_versions"]))
    assert client.patch(f"/api/v1/admin/routes/{route_id}", headers=headers(auth_headers), json={"grade":"6B","expected_version":1}).status_code == 409
    settings = client.get("/api/v1/admin/route-grade-points", headers=auth_headers).json()["items"]
    for item in settings:
        item["points"] = 1000
    assert client.put("/api/v1/admin/route-grade-points", headers=headers(auth_headers), json={"items":settings}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Route, uuid.UUID(route_id)).points == 45
    assert client.delete(f"/api/v1/admin/routes/{route_id}?expected_version=1", headers=headers(auth_headers)).status_code == 200
    assert client.delete(f"/api/v1/admin/route-groups/{group['id']}?expected_version=1", headers=headers(auth_headers)).status_code == 200
    assert client.get("/api/v1/admin/route-groups").status_code == 401



def test_create_categories_then_75_unassigned_routes(client, festival, auth_headers):
    category = client.post("/api/v1/admin/route-groups", headers=headers(auth_headers), json={"items":[{
        "from_grade":"5C+", "to_grade":"6A", "points":15, "color":"#ffff00"
    }]})
    assert category.status_code == 201
    group = category.json()[0]
    assert group["route_count"] == 0
    operation = headers(auth_headers)
    created = client.post("/api/v1/admin/routes/bulk", headers=operation, json={"count":75})
    assert created.status_code == 201, created.text
    rows = created.json()
    assert len(rows) == 75
    assert all(r["group_id"] is None and r["points"] == 0 and r["grade"] == "Не назначена" for r in rows)
    assert [r["number"] for r in rows] == list(range(3,78))
    assert client.post("/api/v1/admin/routes/bulk", headers=operation, json={"count":75}).json() == rows
    first = rows[0]
    assigned = client.patch(f"/api/v1/admin/routes/{first['id']}", headers=headers(auth_headers), json={"group_id":group["id"],"expected_version":first["version"]})
    assert assigned.status_code == 200
    assert assigned.json()["points"] == 15
    assert assigned.json()["grade"] == "5C+–6A"
    with SessionLocal() as db:
        assert db.get(Route, uuid.UUID(rows[1]["id"])).points == 0
        assert db.get(Route, uuid.UUID(rows[1]["id"])).group_id is None
