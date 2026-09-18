from conftest import refresh_publication

import uuid

import pytest

from app.schemas import PublicDisplaySettings


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
    refresh_publication()
    public = client.get("/api/v1/public/results").json()
    assert (public["qualification_refresh_seconds"], public["final_refresh_seconds"]) == (45, 7)
    assert client.patch(url, json=payload).status_code == 401


@pytest.mark.parametrize("value", [0, 2, 301, 3.5, True, "10"])
def test_public_refresh_validation(client, festival, auth_headers, value):
    response = client.patch("/api/v1/admin/event/public-refresh",
        headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())},
        json={"qualification_refresh_seconds": value, "final_refresh_seconds": 10, "expected_version": 1})
    assert response.status_code == 422


def test_public_display_defaults_save_and_live_publication(client, festival, auth_headers):
    url = "/api/v1/admin/event/public-refresh"
    event = client.get("/api/v1/admin/event", headers=auth_headers).json()
    defaults = PublicDisplaySettings().model_dump()
    assert event["public_display_settings"] == defaults
    refresh_publication()
    before = client.get("/api/v1/public/results").json()
    assert before["public_display_settings"] == defaults
    settings = {**defaults, "tv_interval_seconds": 25, "tv_teams": True,
                "sponsors_enabled": False, "tv_rows_per_column": 12, "tv_highlight_top": 0}
    payload = {"qualification_refresh_seconds": 45, "final_refresh_seconds": 7,
               "expected_version": event["version"], "public_display_settings": settings}
    headers = {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}
    saved = client.patch(url, headers=headers, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["public_display_settings"] == settings
    assert saved.json()["version"] == event["version"] + 1
    assert client.patch(url, headers=headers, json=payload).json() == saved.json()
    assert client.patch(url, headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())}, json=payload).status_code == 409
    assert client.get("/api/v1/admin/event", headers=auth_headers).json()["public_display_settings"] == settings
    public = client.get("/api/v1/public/results", params={"publication_version": before["publication_version"]}).json()
    assert public["publication_version"] == before["publication_version"]
    assert public["public_display_settings"] == settings
    # Legacy refresh-only clients preserve the separately configured preferences.
    del payload["public_display_settings"]
    payload["expected_version"] = saved.json()["version"]
    legacy = client.patch(url, headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())}, json=payload)
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["public_display_settings"] == settings


@pytest.mark.parametrize("field,minimum,maximum", [
    ("tv_interval_seconds", 5, 120), ("tv_rows_per_column", 5, 30),
    ("tv_max_columns", 1, 2), ("tv_controls_hide_seconds", 1, 30),
    ("tv_highlight_top", 0, 100), ("sponsor_featured_seconds", 10, 300),
    ("sponsor_regular_seconds", 10, 300), ("tv_sponsor_featured_seconds", 10, 300),
    ("tv_sponsor_regular_seconds", 10, 300),
])
def test_public_display_boundaries(client, festival, auth_headers, field, minimum, maximum):
    from pydantic import ValidationError
    for value in (minimum, maximum):
        assert getattr(PublicDisplaySettings(**{field: value}), field) == value
    for value in (minimum - 1, maximum + 1, True, str(minimum), minimum + 0.5):
        with pytest.raises(ValidationError):
            PublicDisplaySettings(**{field: value})
    response = client.patch("/api/v1/admin/event/public-refresh",
        headers={**auth_headers, "X-Operation-Id": str(uuid.uuid4())},
        json={"qualification_refresh_seconds": 30, "final_refresh_seconds": 10,
              "expected_version": 1, "public_display_settings": {field: maximum + 1}})
    assert response.status_code == 422
