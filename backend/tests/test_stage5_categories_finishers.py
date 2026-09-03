import uuid

from app.db import SessionLocal
from app.models import Participant


def command_headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def category(name, sex, minimum, maximum, **medals):
    return {
        "name": name, "sex": sex, "min_age": minimum, "max_age": maximum,
        "finalist_count": medals.get("finalist_count", 10),
        "bronze_min_points": medals.get("bronze_min"), "bronze_max_points": medals.get("bronze_max"),
        "silver_min_points": medals.get("silver_min"), "silver_max_points": medals.get("silver_max"),
        "gold_min_points": medals.get("gold_min"), "gold_max_points": medals.get("gold_max"),
    }


def test_category_validation_preview_and_finisher_medal(client, festival, auth_headers):
    participant = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Финишеров", "name": "Федор",
            "birth_date": "1994-05-06", "sex": "male", "sport_rank": "Без разряда",
            "club": "Медальный клуб", "representative": "", "merch_size": None,
        },
    ).json()
    checked_in = client.post(
        f"/api/v1/admin/participants/{participant['id']}/check-in", headers=command_headers(auth_headers),
        json={"expected_version": participant["version"]},
    )
    assert checked_in.status_code == 200, checked_in.text
    participant = checked_in.json()
    result = client.put(
        f"/api/v1/admin/participants/{participant['id']}/results", headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(item) for item in festival["route_ids"]], "expected_version": participant["version"]},
    )
    assert result.status_code == 200, result.text

    current = client.get("/api/v1/admin/categories", headers=auth_headers)
    assert current.status_code == 200, current.text
    by_sex = {item["sex"]: item for item in current.json()["categories"]}
    payload = {"categories": [
        category("Мальчики 7-18", "male", 7, 18),
        {**category("Мужчины", "male", 19, None, bronze_min=100, bronze_max=199,
                    silver_min=200, silver_max=299, gold_min=300),
         "id": by_sex["male"]["id"], "expected_version": by_sex["male"]["expected_version"]},
        category("Девочки 7-18", "female", 7, 18),
        {**category("Женщины", "female", 19, None),
         "id": by_sex["female"]["id"], "expected_version": by_sex["female"]["expected_version"]},
    ]}
    preview = client.post("/api/v1/admin/categories/preview", headers=auth_headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["unassigned_participants"] == 0
    saved = client.put("/api/v1/admin/categories", headers=command_headers(auth_headers), json=payload)
    assert saved.status_code == 200, saved.text

    public = client.get("/api/v1/public/results").json()["results"]
    row = next(item for item in public if item["participant_id"] == participant["id"])
    assert row["place"] == 1
    assert row["medal"] == "gold"
    assert row["is_finisher"] is True
    assert row["is_finalist"] is True
    with SessionLocal() as db:
        unchanged = db.get(Participant, uuid.UUID(participant["id"]))
        assert unchanged.birth_date.isoformat() == "1994-05-06"
        assert unchanged.surname == "Финишеров"


def test_category_preview_rejects_age_gaps_and_medal_overlaps(client, festival, auth_headers):
    gap = {"categories": [
        category("Мальчики 7-9", "male", 7, 9), category("Мужчины", "male", 11, None),
        category("Девочки 7-18", "female", 7, 18), category("Женщины", "female", 19, None),
    ]}
    response = client.post("/api/v1/admin/categories/preview", headers=auth_headers, json=gap)
    assert response.status_code == 422
    assert "пропуск" in response.json()["detail"]

    overlap = {"categories": [
        category("Мальчики 7-18", "male", 7, 18),
        category("Мужчины", "male", 19, None, bronze_min=100, bronze_max=200, silver_min=200, silver_max=300),
        category("Девочки 7-18", "female", 7, 18), category("Женщины", "female", 19, None),
    ]}
    response = client.post("/api/v1/admin/categories/preview", headers=auth_headers, json=overlap)
    assert response.status_code == 422
    assert "пересекаются" in response.json()["detail"]


def test_configured_finalist_count_expands_on_tie(client, festival, auth_headers):
    participants = []
    for index, routes in enumerate((festival["route_ids"], festival["route_ids"], festival["route_ids"][:1]), start=1):
        participant = client.post(
            "/api/v1/admin/participants", headers=command_headers(auth_headers),
            json={
                "set_id": str(festival["first_set_id"]), "surname": f"Финалист{index}", "name": "Тест",
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
        participants.append(participant["id"])

    current = client.get("/api/v1/admin/categories", headers=auth_headers).json()["categories"]
    by_sex = {item["sex"]: item for item in current}
    payload = {"categories": [
        category("Мальчики 7-18", "male", 7, 18),
        {**category("Мужчины", "male", 19, None, finalist_count=1),
         "id": by_sex["male"]["id"], "expected_version": by_sex["male"]["expected_version"]},
        category("Девочки 7-18", "female", 7, 18),
        {**category("Женщины", "female", 19, None),
         "id": by_sex["female"]["id"], "expected_version": by_sex["female"]["expected_version"]},
    ]}
    saved = client.put("/api/v1/admin/categories", headers=command_headers(auth_headers), json=payload)
    assert saved.status_code == 200, saved.text

    rows = {row["participant_id"]: row for row in client.get("/api/v1/public/results").json()["results"]}
    assert rows[participants[0]]["is_finalist"] is True
    assert rows[participants[1]]["is_finalist"] is True
    assert rows[participants[2]]["is_finalist"] is False
