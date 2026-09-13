import uuid

import pytest


def test_public_refresh_save_replay_conflict(client, festival, auth_headers):
    url = "/api/v1/admin/event/public-refresh"
    event = client.get("/api/v1/admin/event", headers=auth_headers).json()
    assert (event["qualification_refresh_seconds"], event["final_refresh_seconds"]) == (30, 10)
    payload = {"qualification_refresh_seconds": 45, "final_refresh_seconds": 7, "expected_version": event["version"]}
    headers = {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}
    saved = client.patch(url, headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert client.patch(url, headers=headers, json=payload).json() == saved.json()
    conflict = client.patch(url, headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())}, json=payload)
    assert conflict.status_code == 409
    public = client.get("/api/v1/public/results").json()
    assert (public["qualification_refresh_seconds"], public["final_refresh_seconds"]) == (45, 7)
    assert client.patch(url, json=payload).status_code == 401


@pytest.mark.parametrize("value", [0, 2, 301, 3.5, True, "10"])
def test_public_refresh_validation(client, festival, auth_headers, value):
    response = client.patch("/api/v1/admin/event/public-refresh",
        headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())},
        json={"qualification_refresh_seconds": value, "final_refresh_seconds": 10, "expected_version": 1})
    assert response.status_code == 422
