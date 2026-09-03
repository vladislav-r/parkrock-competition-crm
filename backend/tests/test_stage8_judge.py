import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, AgeGroup, FinalRoute, UserRole
from app.security import hash_password


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
