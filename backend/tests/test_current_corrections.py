import uuid
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Ascent, Club, Participant, Route, Sex


def operation_headers(auth_headers: dict[str, str]) -> dict[str, str]:
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def test_grade_points_are_shared_nullable_and_nonnegative(client, festival, auth_headers):
    response = client.get("/api/v1/admin/route-grade-points", headers=auth_headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 24
    assert all(item["points"] is None and item["effective_points"] == 0 for item in items)
    assert [item["grade"] for item in items[:6]] == ["5A", "5A+", "5B", "5B+", "5C", "5C+"]

    values = {item["grade"]: None for item in items}
    values.update({"5A": 300, "5A+": 10, "5B": 75, "6A": 0})
    payload = [{
        "grade": item["grade"], "points": values[item["grade"]],
        "expected_version": item["expected_version"],
    } for item in items]
    preview = client.post("/api/v1/admin/route-grade-points/preview", headers=auth_headers, json={"items": payload})
    assert preview.status_code == 200, preview.text
    assert preview.json()["changed_grades"] == 4
    assert preview.json()["affected_routes"] == 2

    updated = client.put(
        "/api/v1/admin/route-grade-points", headers=operation_headers(auth_headers), json={"items": payload},
    )
    assert updated.status_code == 200, updated.text
    updated_values = {item["grade"]: item["points"] for item in updated.json()["items"]}
    assert updated_values["5A"] == 300
    assert updated_values["5A+"] == 10
    assert updated_values["6A"] == 0
    with SessionLocal() as db:
        routes = {item.grade: item.points for item in db.scalars(select(Route).where(
            Route.event_id == festival["event_id"],
        )).all()}
        assert routes == {"5B": 75, "6A": 0}

    invalid = [{**item, "points": -1} if item["grade"] == "5A" else item for item in payload]
    rejected = client.post("/api/v1/admin/route-grade-points/preview", headers=auth_headers, json={"items": invalid})
    assert rejected.status_code == 422


def test_routes_can_be_created_in_bulk_and_only_unused_route_can_be_deleted(client, festival, auth_headers):
    created = client.post(
        "/api/v1/admin/routes/bulk", headers=operation_headers(auth_headers),
        json={"count": 3, "grade": "7A"},
    )
    assert created.status_code == 201, created.text
    assert [item["number"] for item in created.json()] == [3, 4, 5]
    assert all(item["grade"] == "7A" for item in created.json())

    unused = created.json()[0]
    deleted = client.delete(
        f"/api/v1/admin/routes/{unused['id']}?expected_version={unused['version']}",
        headers=operation_headers(auth_headers),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "deleted", "number": 3}

    with SessionLocal() as db:
        remaining = list(db.scalars(select(Route).where(
            Route.event_id == festival["event_id"],
        ).order_by(Route.number)).all())
        assert [route.number for route in remaining] == [1, 2, 3, 4]
        assert [route.sort_order for route in remaining] == [1, 2, 3, 4]
        used_version = db.get(Route, uuid.UUID(created.json()[1]["id"])).version
        club = db.scalar(select(Club).where(Club.event_id == festival["event_id"]))
        participant = Participant(
            event_id=festival["event_id"], club_id=club.id, set_id=festival["first_set_id"],
            start_number=99, surname="Тест", name="Удаление", birth_date=date(2000, 1, 1),
            sex=Sex.male, club="Тестовый клуб",
        )
        db.add(participant)
        db.flush()
        db.add(Ascent(participant_id=participant.id, route_id=created.json()[1]["id"], is_completed=True))
        db.commit()

    used = created.json()[1]
    rejected = client.delete(
        f"/api/v1/admin/routes/{used['id']}?expected_version={used_version}",
        headers=operation_headers(auth_headers),
    )
    assert rejected.status_code == 409
    assert "прохождения" in rejected.json()["detail"]


def test_all_unused_routes_can_be_deleted_at_once(client, festival, auth_headers):
    deleted = client.delete("/api/v1/admin/routes", headers=operation_headers(auth_headers))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 2}

    with SessionLocal() as db:
        assert db.scalars(select(Route).where(Route.event_id == festival["event_id"])).all() == []
