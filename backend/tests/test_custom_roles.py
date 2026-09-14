from urllib.parse import quote

from test_roles_and_audit import create_user, login_headers, operation_headers


def test_custom_role_lifecycle(client, festival, auth_headers):
    headers = operation_headers(auth_headers)
    payload = {"name": "  Волонтёр   фестиваля "}
    created = client.post("/api/v1/admin/roles", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    role = created.json()["role"]
    assert role == "Волонтёр фестиваля"
    assert created.json()["permissions"] == []
    assert client.post("/api/v1/admin/roles", headers=headers, json=payload).json() == created.json()
    for name in [role.lower(), "Администратор", "administrator"]:
        assert client.post("/api/v1/admin/roles", headers=operation_headers(auth_headers), json={"name": name}).status_code == 409
    for name in ["  ", "a/b", "x" * 51]:
        assert client.post("/api/v1/admin/roles", headers=operation_headers(auth_headers), json={"name": name}).status_code == 422
    assert create_user(client, auth_headers, role="administrator", email="second@example.com").status_code == 201
    assert create_user(client, auth_headers, role="несуществующая").status_code == 422
    user = create_user(client, auth_headers, role=role)
    assert user.status_code == 201, user.text
    staff = login_headers(client, "reception@example.com")
    assert client.get("/api/v1/auth/me", headers=staff).json()["permissions"] == []
    assert client.get("/api/v1/admin/participants", headers=staff).status_code == 403
    assert client.post("/api/v1/admin/roles", headers=operation_headers(staff), json={"name": "Другая"}).status_code == 403
    path = f"/api/v1/admin/roles/{quote(role)}/permissions"
    saved = client.put(path, headers=operation_headers(auth_headers), json={"permissions": ["participants.view", "users.manage"]})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/admin/participants", headers=staff).status_code == 200
    assert role in [item["role"] for item in client.get("/api/v1/admin/roles", headers=staff).json()["roles"]]
    assert client.put(path, headers=operation_headers(staff), json={"permissions": ["roles.manage"]}).status_code == 403
    assert client.put("/api/v1/admin/roles/missing/permissions", headers=operation_headers(auth_headers), json={"permissions": []}).status_code == 422
    audit = client.get("/api/v1/admin/audit?action=role.create", headers=auth_headers).json()
    assert audit["total"] == 1
