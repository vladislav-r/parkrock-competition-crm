import uuid
import asyncio
import httpx

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, AgeGroup, Event, EventStage, FinalCategoryResult, FinalRoute, UserRole
from app.security import hash_password


def test_independent_finalists_save_concurrently_and_replay(client, festival, auth_headers):
    participant, routes = prepare_final(client, festival, auth_headers)
    from app.main import app
    from app.models import Participant, QualificationResultSnapshot, FinalRouteAttempt
    with SessionLocal() as db:
        actor = db.scalar(select(Admin).where(Admin.email == "admin@test.local"))
        actor.assigned_final_route_id = uuid.UUID(routes[0]["id"])
        original = db.get(Participant, uuid.UUID(participant["id"]))
        original_result = db.scalar(select(FinalCategoryResult))
        original_snapshot = db.get(QualificationResultSnapshot, original_result.qualification_result_snapshot_id)
        ids = [str(original_result.id)]
        for i in range(1, 8):
            p = Participant(event_id=original.event_id, club_id=original.club_id, set_id=original.set_id,
                start_number=100+i, surname=f"Parallel{i}", name="Test", birth_date=original.birth_date,
                sex=original.sex, club=original.club)
            db.add(p); db.flush()
            q = QualificationResultSnapshot(event_id=p.event_id, category_snapshot_id=original_snapshot.category_snapshot_id,
                participant_id=p.id, start_number=p.start_number, surname=p.surname, name=p.name, club=p.club,
                completed_count=1, points=100, place=i+1, is_finalist=True, exit_order=i+1)
            db.add(q); db.flush()
            result = FinalCategoryResult(event_id=p.event_id, category_snapshot_id=q.category_snapshot_id,
                qualification_result_snapshot_id=q.id, participant_id=p.id)
            db.add(result); db.flush(); ids.append(str(result.id))
        db.commit()
    commands = [(fid, command_headers(auth_headers), {"expected_version": 1, "zone_attempt": 1, "top_attempt": i+1}) for i, fid in enumerate(ids)]

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            replies = await asyncio.wait_for(asyncio.gather(*[
                api.put(f"/api/v1/judge/results/{fid}", headers=headers, json=body)
                for fid, headers, body in commands]), 15)
            assert [r.status_code for r in replies] == [200]*8
            replay = await asyncio.gather(*[
                api.put(f"/api/v1/judge/results/{fid}", headers=headers, json=body)
                for fid, headers, body in commands])
            assert [r.json() for r in replay] == [r.json() for r in replies]
    asyncio.run(run())
    with SessionLocal() as db:
        assert len(list(db.scalars(select(FinalRouteAttempt)))) == 8
        assert {r.version for r in db.scalars(select(FinalCategoryResult))} == {2}


def test_another_judge_route_does_not_invalidate_unsent_result(client, festival, auth_headers):
    _, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        for i in range(2):
            db.add(Admin(email=f"parallel-judge{i}@test.local", full_name=f"Judge {i}",
                password_hash=hash_password("judge-password"), role=UserRole.route_judge,
                assigned_final_route_id=uuid.UUID(routes[i]["id"])))
        db.commit()
    headers = [judge_headers(client, f"parallel-judge{i}@test.local") for i in range(2)]
    rows = [client.get("/api/v1/judge/workspace", headers=h).json()["participants"][0] for h in headers]
    for row, h in zip(rows, headers):
        body = {"expected_version": row["version"], "top_attempt": 1}
        url = f"/api/v1/judge/results/{row['final_result_id']}"
        assert client.put(url, headers=command_headers(h), json=body).status_code == 200
        assert client.put(url, headers=command_headers(h), json=body).status_code == 409


def command_headers(auth_headers, operation_id=None):
    return {**auth_headers, "X-Operation-Id": str(operation_id or uuid.uuid4())}


def create_finalist(client, festival, auth_headers):
    participant = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Судейский", "name": "Тест",
            "birth_date": "1994-05-06", "sex": "male", "sport_rank": "Без разряда",
            "club": "Тестовый клуб", "representative": "", "merch_size": None,
        },
    ).json()
    participant = client.post(
        f"/api/v1/admin/participants/{participant['id']}/check-in",
        headers=command_headers(auth_headers), json={"expected_version": participant["version"]},
    ).json()
    response = client.put(
        f"/api/v1/admin/participants/{participant['id']}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(item) for item in festival["route_ids"]], "expected_version": participant["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def prepare_final(client, festival, auth_headers):
    with SessionLocal() as db:
        male = db.scalar(select(AgeGroup).where(AgeGroup.event_id == festival["event_id"], AgeGroup.name == "Мужчины"))
        male.finalist_count = 1
        db.commit()
    participant = create_finalist(client, festival, auth_headers)
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    male = next(item for item in status["categories"] if item["name"] == "Мужчины")
    for category in status["categories"]:
        response = client.post(
            f"/api/v1/admin/final/categories/{category['id']}/confirm",
            headers=command_headers(auth_headers), json={"expected_version": category["expected_version"]},
        )
        assert response.status_code == 200, response.text
        status = response.json()
    response = client.post(
        "/api/v1/admin/final/start", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert response.status_code == 200, response.text
    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    response = client.put(
        f"/api/v1/admin/final/categories/{male['id']}/routes", headers=command_headers(auth_headers),
        json={"expected_event_version": setup["event_version"], "route_ids": [item["id"] for item in setup["routes"][:4]]},
    )
    assert response.status_code == 200, response.text
    return participant, response.json()["routes"]


def judge_headers(client, email):
    response = client.post("/api/v1/auth/login", data={"username": email, "password": "judge-password"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_final_requires_confirmed_results_for_every_category(client, festival, auth_headers):
    _, routes = prepare_final(client, festival, auth_headers)
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    male = next(item for item in status["categories"] if item["name"] == "Мужчины")

    blocked = client.post(
        "/api/v1/admin/final/complete", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert blocked.status_code == 409
    assert "Подтвердите результаты финала" in blocked.json()["detail"]

    confirmed = client.post(
        f"/api/v1/admin/final/categories/{male['id']}/final-confirm",
        headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert next(item for item in confirmed.json()["categories"] if item["id"] == male["id"])["final_confirmed"] is True

    reopened = client.post(
        f"/api/v1/admin/final/categories/{male['id']}/final-reopen",
        headers=command_headers(auth_headers),
        json={"expected_version": confirmed.json()["event_version"]},
    )
    assert reopened.status_code == 200, reopened.text
    assert next(item for item in reopened.json()["categories"] if item["id"] == male["id"])["final_confirmed"] is False

    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    female = next(item for item in setup["categories"] if item["name"] == "Женщины")
    configured = client.put(
        f"/api/v1/admin/final/categories/{female['id']}/routes",
        headers=command_headers(auth_headers),
        json={"expected_event_version": setup["event_version"], "route_ids": [item["id"] for item in routes[:4]]},
    )
    assert configured.status_code == 200, configured.text
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    confirmed_all = client.post(
        "/api/v1/admin/final/final-results/confirm-all",
        headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert confirmed_all.status_code == 200, confirmed_all.text
    assert confirmed_all.json()["all_final_categories_confirmed"] is True

    completed = client.post(
        "/api/v1/admin/final/complete", headers=command_headers(auth_headers),
        json={"expected_version": confirmed_all.json()["event_version"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["stage"] == "completed"


def test_route_judge_can_save_once_only_on_assigned_final_route(client, festival, auth_headers):
    participant, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        first_route = db.get(FinalRoute, uuid.UUID(routes[0]["id"]))
        fifth_route = db.get(FinalRoute, uuid.UUID(routes[4]["id"]))
        db.add_all([
            Admin(email="judge1@test.local", full_name="Судья 1", password_hash=hash_password("judge-password"),
                  role=UserRole.route_judge, assigned_final_route_id=first_route.id),
            Admin(email="judge5@test.local", full_name="Судья 5", password_hash=hash_password("judge-password"),
                  role=UserRole.route_judge, assigned_final_route_id=fifth_route.id),
        ])
        db.commit()

    first_headers = judge_headers(client, "judge1@test.local")
    workspace = client.get("/api/v1/judge/workspace", headers=first_headers)
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["route"]["number"] == 1
    assert len(workspace.json()["participants"]) == 1
    row = workspace.json()["participants"][0]
    assert row["participant_id"] == participant["id"]
    assert row["locked"] is False

    operation_id = uuid.uuid4()
    payload = {"expected_version": row["version"], "zone_attempt": 2, "top_attempt": 3}
    saved = client.put(
        f"/api/v1/judge/results/{row['final_result_id']}",
        headers=command_headers(first_headers, operation_id), json=payload,
    )
    assert saved.status_code == 200, saved.text
    saved_row = saved.json()["participants"][0]
    assert (saved_row["locked"], saved_row["zone_attempt"], saved_row["top_attempt"], saved_row["score"]) == (True, 2, 3, 24.8)

    replay = client.put(
        f"/api/v1/judge/results/{row['final_result_id']}",
        headers=command_headers(first_headers, operation_id), json=payload,
    )
    assert replay.status_code == 200, replay.text
    blocked = client.put(
        f"/api/v1/judge/results/{row['final_result_id']}",
        headers=command_headers(first_headers), json=payload,
    )
    assert blocked.status_code == 409

    fifth_headers = judge_headers(client, "judge5@test.local")
    empty_workspace = client.get("/api/v1/judge/workspace", headers=fifth_headers)
    assert empty_workspace.status_code == 200
    assert empty_workspace.json()["participants"] == []
    forbidden = client.put(
        f"/api/v1/judge/results/{row['final_result_id']}",
        headers=command_headers(fifth_headers), json=payload,
    )
    assert forbidden.status_code == 403


def test_route_judge_cannot_see_or_save_stale_finalists_before_final(client, festival, auth_headers):
    _, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        first_route = db.get(FinalRoute, uuid.UUID(routes[0]["id"]))
        db.add(Admin(
            email="judge-before-final@test.local", full_name="Судья до финала",
            password_hash=hash_password("judge-password"), role=UserRole.route_judge,
            assigned_final_route_id=first_route.id,
        ))
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.preparation
        event.qualification_started_at = None
        event.final_started_at = None
        db.commit()

    headers = judge_headers(client, "judge-before-final@test.local")
    workspace = client.get("/api/v1/judge/workspace", headers=headers)
    assert workspace.status_code == 409
    assert workspace.json()["detail"] == "Рабочее место судьи откроется после запуска финала"

    with SessionLocal() as db:
        stale_result = db.scalar(select(FinalCategoryResult).where(FinalCategoryResult.event_id == festival["event_id"]))
    blocked = client.put(
        f"/api/v1/judge/results/{stale_result.id}", headers=command_headers(headers),
        json={"expected_version": stale_result.version, "zone_attempt": 1, "top_attempt": 1},
    )
    assert blocked.status_code == 409
