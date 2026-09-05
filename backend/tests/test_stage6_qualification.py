import uuid

from sqlalchemy import select

from app import backup_service
from app.db import SessionLocal
from app.models import AgeGroup, FinalCategoryRoute, QualificationResultSnapshot
from app.routers import admin_final


def command_headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def create_result(client, festival, auth_headers, surname, routes):
    participant = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": surname, "name": "Тест",
            "birth_date": "1994-05-06", "sex": "male", "sport_rank": "Без разряда",
            "club": "Тестовый клуб", "representative": "", "merch_size": None,
        },
    ).json()
    participant = client.post(
        f"/api/v1/admin/participants/{participant['id']}/check-in", headers=command_headers(auth_headers),
        json={"expected_version": participant["version"]},
    ).json()
    response = client.put(
        f"/api/v1/admin/participants/{participant['id']}/results", headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(route_id) for route_id in routes], "expected_version": participant["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_confirm_start_snapshot_lock_and_development_cancel(client, festival, auth_headers, monkeypatch):
    with SessionLocal() as db:
        male = db.scalar(select(AgeGroup).where(AgeGroup.event_id == festival["event_id"], AgeGroup.name == "Мужчины"))
        male.finalist_count = 1
        db.add(AgeGroup(event_id=festival["event_id"], name="Мальчики 7-9", sex="male", min_age=7, max_age=9, sort_order=0, finalist_count=0, participates_in_final=False))
        db.commit()

    yakovlev = create_result(client, festival, auth_headers, "Яковлев", festival["route_ids"])
    abramov = create_result(client, festival, auth_headers, "Абрамов", festival["route_ids"])
    outsider = create_result(client, festival, auth_headers, "Внефинала", festival["route_ids"][:1])

    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    male_category = next(item for item in status["categories"] if item["name"] == "Мужчины")
    review = client.get(
        f"/api/v1/admin/final/categories/{male_category['id']}/results", headers=auth_headers,
    )
    assert review.status_code == 200, review.text
    assert [item["surname"] if "surname" in item else item["full_name"].split()[0] for item in review.json()["results"]] == [
        "Яковлев", "Абрамов", "Внефинала",
    ]
    assert sum(item["is_finalist"] for item in review.json()["results"]) == 2
    blocked = client.post(
        "/api/v1/admin/final/start", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert blocked.status_code == 409
    assert "Подтвердите" in blocked.json()["detail"]

    for category in status["categories"]:
        response = client.post(
            f"/api/v1/admin/final/categories/{category['id']}/confirm", headers=command_headers(auth_headers),
            json={"expected_version": category["expected_version"]},
        )
        assert response.status_code == 200, response.text
        status = response.json()
    assert status["all_categories_confirmed"] is True

    started = client.post(
        "/api/v1/admin/final/start", headers=command_headers(auth_headers),
        json={"expected_version": status["event_version"]},
    )
    assert started.status_code == 200, started.text
    started_status = started.json()
    assert started_status["stage"] == "final"
    assert started_status["snapshot_results"] == 3
    assert started_status["snapshot_finalists"] == 2

    public_after_start = client.get("/api/v1/public/results").json()
    assert "Мужчины" in public_after_start["final_groups"]
    public_order = client.get("/api/v1/public/final-results", params={"group": "Мужчины"})
    assert public_order.status_code == 200, public_order.text
    assert public_order.json()["routes"] == []
    assert [item["exit_order"] for item in public_order.json()["results"]] == [1, 2]
    assert all(item["has_result"] is False for item in public_order.json()["results"])

    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers)
    assert setup.status_code == 200, setup.text
    setup_data = setup.json()
    assert len(setup_data["routes"]) == 8
    assert all(item["name"] != "Мальчики 7-9" for item in setup_data["categories"])
    configured = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/routes", headers=command_headers(auth_headers),
        json={"expected_event_version": setup_data["event_version"], "route_ids": [item["id"] for item in setup_data["routes"][:4]]},
    )
    assert configured.status_code == 200, configured.text
    final_results = client.get(
        f"/api/v1/admin/final/categories/{male_category['id']}/final-results", headers=auth_headers,
    )
    assert final_results.status_code == 200, final_results.text
    assert {item["full_name"].split()[0] for item in final_results.json()["results"]} == {"Яковлев", "Абрамов"}
    assert [(item["full_name"].split()[0], item["exit_order"], item["has_result"]) for item in final_results.json()["results"]] == [
        ("Абрамов", 1, False), ("Яковлев", 2, False),
    ]
    yakovlev_result = next(item for item in final_results.json()["results"] if item["full_name"].startswith("Яковлев"))
    route_ids = [item["id"] for item in final_results.json()["routes"]]
    zero_yakovlev = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/participants/{yakovlev_result['participant_id']}/final-results",
        headers=command_headers(auth_headers),
        json={"expected_version": yakovlev_result["version"], "attempts": [
            {"route_id": route_id, "zone_attempt": None, "top_attempt": None} for route_id in route_ids
        ]},
    )
    assert zero_yakovlev.status_code == 200, zero_yakovlev.text
    assert [(item["full_name"].split()[0], item["has_result"]) for item in zero_yakovlev.json()["results"]] == [
        ("Яковлев", True), ("Абрамов", False),
    ]
    yakovlev_result = zero_yakovlev.json()["results"][0]
    saved_yakovlev = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/participants/{yakovlev_result['participant_id']}/final-results",
        headers=command_headers(auth_headers),
        json={"expected_version": yakovlev_result["version"], "attempts": [
            {"route_id": route_ids[0], "zone_attempt": 2, "top_attempt": 3},
            {"route_id": route_ids[1], "zone_attempt": 2, "top_attempt": None},
            {"route_id": route_ids[2], "zone_attempt": None, "top_attempt": None},
            {"route_id": route_ids[3], "zone_attempt": None, "top_attempt": None},
        ]},
    )
    assert saved_yakovlev.status_code == 200, saved_yakovlev.text
    yakovlev_row = next(item for item in saved_yakovlev.json()["results"] if item["full_name"].startswith("Яковлев"))
    assert (yakovlev_row["score"], yakovlev_row["top_count"], yakovlev_row["zone_count"], yakovlev_row["top_attempts"], yakovlev_row["zone_attempts"]) == (34.7, 1, 2, 3, 4)
    blocked_reassignment = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/routes", headers=command_headers(auth_headers),
        json={"expected_event_version": configured.json()["event_version"], "route_ids": [item["id"] for item in setup_data["routes"][4:]]},
    )
    assert blocked_reassignment.status_code == 409
    blocked_participation = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/participation", headers=command_headers(auth_headers),
        json={"expected_event_version": configured.json()["event_version"], "participates": False},
    )
    assert blocked_participation.status_code == 409
    abramov_result = next(item for item in saved_yakovlev.json()["results"] if item["full_name"].startswith("Абрамов"))
    saved_abramov = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/participants/{abramov_result['participant_id']}/final-results",
        headers=command_headers(auth_headers),
        json={"expected_version": abramov_result["version"], "attempts": [
            {"route_id": route_id, "zone_attempt": None, "top_attempt": 1} for route_id in route_ids
        ]},
    )
    assert saved_abramov.status_code == 200, saved_abramov.text
    assert [(item["full_name"].split()[0], item["place"], item["score"]) for item in saved_abramov.json()["results"]] == [
        ("Абрамов", 1, 100.0), ("Яковлев", 2, 34.7),
    ]
    public_final = client.get("/api/v1/public/final-results", params={"group": "Мужчины"})
    assert public_final.status_code == 200, public_final.text
    public_rows = public_final.json()["results"]
    assert [(item["full_name"].split()[0], item["place"], item["score"]) for item in public_rows] == [
        ("Абрамов", 1, 100.0), ("Яковлев", 2, 34.7),
    ]
    assert public_rows[1]["attempts"][0] == {"route_number": 1, "zone_attempt": 2, "top_attempt": 3}

    snapshot_review = client.get(
        f"/api/v1/admin/final/categories/{male_category['id']}/results", headers=auth_headers,
    )
    assert snapshot_review.status_code == 200, snapshot_review.text
    assert {item["full_name"].split()[0]: item["exit_order"] for item in snapshot_review.json()["results"]} == {
        "Яковлев": 2, "Абрамов": 1, "Внефинала": None,
    }
    exported = client.get(
        f"/api/v1/admin/final/categories/{male_category['id']}/snapshot.csv", headers=auth_headers,
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.content.startswith("\ufeffВозрастная группа: Мужчины\r\n\r\nМесто;Порядок выхода".encode())
    assert "Абрамов Тест".encode() in exported.content

    with SessionLocal() as db:
        finalists = list(db.scalars(select(QualificationResultSnapshot).where(
            QualificationResultSnapshot.is_finalist.is_(True)).order_by(QualificationResultSnapshot.exit_order)).all())
        assert [(item.surname, item.place, item.exit_order) for item in finalists] == [
            ("Абрамов", 1, 1), ("Яковлев", 1, 2),
        ]

        next(item for item in finalists if item.surname == "Яковлев").place = 8
        db.commit()

    yakovlev_result = next(item for item in saved_abramov.json()["results"] if item["full_name"].startswith("Яковлев"))
    tied_yakovlev = client.put(
        f"/api/v1/admin/final/categories/{male_category['id']}/participants/{yakovlev_result['participant_id']}/final-results",
        headers=command_headers(auth_headers),
        json={"expected_version": yakovlev_result["version"], "attempts": [
            {"route_id": route_id, "zone_attempt": None, "top_attempt": 1} for route_id in route_ids
        ]},
    )
    assert tied_yakovlev.status_code == 200, tied_yakovlev.text
    assert [(item["full_name"].split()[0], item["qualification_place"], item["place"], item["score"])
            for item in tied_yakovlev.json()["results"]] == [
        ("Абрамов", 1, 1, 100.0), ("Яковлев", 8, 2, 100.0),
    ]

    locked = client.put(
        f"/api/v1/admin/participants/{outsider['id']}/results", headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(item) for item in festival["route_ids"]], "expected_version": outsider["version"]},
    )
    assert locked.status_code == 409
    assert "заблокированы" in locked.json()["detail"]

    judge = client.post(
        "/api/v1/admin/users", headers=command_headers(auth_headers),
        json={
            "email": "persistent-judge@example.com", "full_name": "Постоянный судья",
            "password": "safe-password", "role": "route_judge",
            "assigned_final_route_id": route_ids[0],
        },
    )
    assert judge.status_code == 201, judge.text

    created_backups = []
    monkeypatch.setattr(admin_final, "_test_database", lambda db: False)
    monkeypatch.setattr(
        backup_service, "create_backup",
        lambda db, **kwargs: created_backups.append(kwargs) or {"filename": "test-pre-rollback.dump"},
    )

    cancelled = client.post(
        "/api/v1/admin/final/cancel", headers=command_headers(auth_headers),
        json={"expected_version": configured.json()["event_version"]},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["stage"] == "qualification"
    assert cancelled.json()["snapshot_results"] == 0
    with SessionLocal() as db:
        preserved_route_ids = {
            str(item) for item in db.scalars(select(FinalCategoryRoute.final_route_id).where(
                FinalCategoryRoute.age_group_id == uuid.UUID(male_category["id"]),
            )).all()
        }
    assert preserved_route_ids == set(route_ids)
    preserved_users = client.get("/api/v1/admin/users", headers=auth_headers).json()
    preserved_judge = next(item for item in preserved_users if item["email"] == "persistent-judge@example.com")
    assert preserved_judge["assigned_final_route_id"] == route_ids[0]
    assert created_backups[0]["source"] == "pre-rollback"
