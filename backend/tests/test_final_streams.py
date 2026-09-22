from conftest import refresh_publication
import uuid
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (Admin, Event, AgeGroup, FinalCategoryResult, FinalCategoryRoute,
                        FinalRouteAttempt, Participant, QualificationCategorySnapshot,
                        QualificationResultSnapshot)
from app.routers.admin_competition import _clear_final_results, _clear_final_setup
from test_stage8_judge import prepare_final, command_headers


def test_stream_routes_order_locks_replay_and_reset(client, festival, auth_headers):
    _, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        female = db.scalar(select(AgeGroup).where(AgeGroup.name == "Женщины"))
        male = db.scalar(select(AgeGroup).where(AgeGroup.name == "Мужчины"))
        female_id, male_id = str(female.id), str(male.id)
        cat = db.scalar(select(QualificationCategorySnapshot).where(QualificationCategorySnapshot.age_group_id == female.id))
        original = db.scalar(select(Participant))
        # Insert in reverse exit order to ensure the judge sorts inside the category, too.
        for i in [2, 1]:
            p = Participant(event_id=original.event_id, club_id=original.club_id, set_id=original.set_id,
                start_number=100+i, surname=f"Финалистка{i}", name="Тест", birth_date=original.birth_date,
                sex="female", club=original.club)
            db.add(p); db.flush()
            q = QualificationResultSnapshot(event_id=p.event_id, category_snapshot_id=cat.id,
                participant_id=p.id, start_number=p.start_number, surname=p.surname, name=p.name, club=p.club,
                completed_count=1, points=100, place=i, is_finalist=True, exit_order=i)
            db.add(q); db.flush()
            db.add(FinalCategoryResult(event_id=p.event_id, category_snapshot_id=cat.id,
                qualification_result_snapshot_id=q.id, participant_id=p.id))
        db.get(Admin, festival["admin_id"]).assigned_final_route_id = uuid.UUID(routes[0]["id"])
        db.commit()

    def setup():
        r = client.get("/api/v1/admin/final/setup", headers=auth_headers)
        assert r.status_code == 200, r.text
        return r.json()

    def move(gid, stream, before=None, version=None, headers=None):
        return client.put(f"/api/v1/admin/final/categories/{gid}/stream", headers=headers or command_headers(auth_headers),
            json={"expected_event_version": version or setup()["event_version"], "stream_number": stream, "before_category_id": before})

    def order(stream):
        return [c["id"] for c in sorted(setup()["categories"], key=lambda c: c["stream_order"] or 0) if c["stream_number"] == stream]

    assert move(female_id, 1).status_code == 200
    assert order(1) == [male_id, female_id]
    assert move(female_id, 1, male_id).status_code == 200
    assert order(1) == [female_id, male_id]
    workspace = client.get("/api/v1/judge/workspace", headers=auth_headers).json()
    assert [(p["category_id"], p["exit_order"]) for p in workspace["participants"]] == [(female_id, 1), (female_id, 2), (male_id, 1)]

    headers, version = command_headers(auth_headers), setup()["event_version"]
    moved = move(female_id, 2, version=version, headers=headers)
    assert moved.status_code == 200, moved.text
    assert move(female_id, 2, version=version, headers=headers).json() == moved.json()
    assert move(female_id, 1, version=version).status_code == 409
    category = next(c for c in setup()["categories"] if c["id"] == female_id)
    assert set(category["route_ids"]) == {r["id"] for r in routes[4:]}
    assert [p["category_id"] for p in client.get("/api/v1/judge/workspace", headers=auth_headers).json()["participants"]] == [male_id]
    public_rows = client.get(f"/api/v1/admin/final/categories/{female_id}/final-results", headers=auth_headers).json()
    assert [r["number"] for r in public_rows["routes"]] == [5, 6, 7, 8]
    refresh_publication()
    public = client.get("/api/v1/public/final-results", params={"group": "Женщины"})
    assert public.status_code == 200, public.text
    assert [r["number"] for r in public.json()["routes"]] == [5, 6, 7, 8]
    assert move(female_id, 3).status_code == 422
    assert move(female_id, 1, str(uuid.uuid4())).status_code == 422
    assert move(female_id, None).status_code == 200
    unassigned = client.get(f"/api/v1/admin/final/categories/{female_id}/final-results", headers=auth_headers)
    assert unassigned.status_code == 200, unassigned.text
    assert unassigned.json()["routes"] == [] and unassigned.json()["results"] == []
    assert next(c for c in setup()["categories"] if c["id"] == female_id)["route_ids"] == []
    assert move(female_id, 1).status_code == 200

    # Even a saved zero score is a result and must protect the assignment.
    with SessionLocal() as db:
        result = db.scalar(select(FinalCategoryResult).join(QualificationCategorySnapshot,
            QualificationCategorySnapshot.id == FinalCategoryResult.category_snapshot_id)
            .where(QualificationCategorySnapshot.age_group_id == uuid.UUID(male_id)))
        db.add(FinalRouteAttempt(event_id=festival["event_id"], final_category_result_id=result.id,
                                final_route_id=uuid.UUID(routes[0]["id"])))
        db.commit()
    assert next(c for c in setup()["categories"] if c["id"] == male_id)["assignment_locked"]
    assert move(male_id, 2).status_code == 409
    assert move(female_id, 1, male_id).status_code == 409  # Would shift a locked category.
    assert move(female_id, 2).status_code == 200
    with SessionLocal() as db:
        _clear_final_results(db, db.get(Event, festival["event_id"])); db.commit()
    assert move(male_id, 2).status_code == 200
    with SessionLocal() as db:
        _clear_final_setup(db, db.get(Event, festival["event_id"])); db.commit()
        assert not list(db.scalars(select(FinalCategoryRoute)))
    assert all(c["stream_number"] is None and c["stream_order"] is None for c in setup()["categories"])
