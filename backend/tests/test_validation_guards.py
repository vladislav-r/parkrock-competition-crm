import uuid


def operation_headers(auth_headers: dict[str, str]) -> dict[str, str]:
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def test_set_and_route_names_cannot_be_only_whitespace(client, festival, auth_headers):
    created_set = client.post(
        "/api/v1/admin/sets",
        headers=operation_headers(auth_headers),
        json={"name": "   ", "start_time": "17:00", "end_time": "18:00", "capacity": 10},
    )
    assert created_set.status_code == 422, created_set.text

    created_route = client.post(
        "/api/v1/admin/routes",
        headers=operation_headers(auth_headers),
        json={"name": "   ", "grade": "6A"},
    )
    assert created_route.status_code == 422, created_route.text


def test_password_cannot_be_only_whitespace(client, festival, auth_headers):
    created = client.post(
        "/api/v1/admin/users",
        headers=operation_headers(auth_headers),
        json={
            "email": "spaces@example.com",
            "full_name": "Пробельный пароль",
            "password": "        ",
            "role": "secretary",
        },
    )
    assert created.status_code == 422, created.text

    updated = client.patch(
        f"/api/v1/admin/users/{festival['admin_id']}",
        headers=operation_headers(auth_headers),
        json={"expected_version": 1, "password": "        "},
    )
    assert updated.status_code == 422, updated.text


def test_manual_participant_rejects_unknown_merch_size(client, festival, auth_headers):
    response = client.post(
        "/api/v1/admin/participants",
        headers=operation_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]),
            "surname": "Размеров",
            "name": "Неверный",
            "birth_date": "1995-01-01",
            "sex": "male",
            "sport_rank": "Без разряда",
            "club": "Тестовый клуб",
            "representative": "",
            "merch_size": "4XL",
        },
    )
    assert response.status_code == 422, response.text
