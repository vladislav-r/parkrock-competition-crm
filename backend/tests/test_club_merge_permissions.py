import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import backup_service
from app.db import SessionLocal
from app.models import Admin, Club, Participant, RolePermission, UserRole
from app.permissions import Permission, effective_permissions
from test_stage4_reception_clubs import command_headers, create_participant

REAL_CREATE_BACKUP = backup_service.create_backup


@pytest.fixture
def merge_case(client, festival, auth_headers, monkeypatch):
    first = create_participant(client, festival, auth_headers, "Первый", club="Скала", representative="Анна")
    second = create_participant(client, festival, auth_headers, "Второй", club="Горы", representative="Иван")
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers).json()
    source = next(item for item in clubs if item["id"] == first["club_id"])
    target = next(item for item in clubs if item["id"] == second["club_id"])
    backups = []
    def backup(db, **kwargs):
        # A separate connection still sees the original, committed clubs and membership.
        with SessionLocal() as before:
            assert before.get(Participant, uuid.UUID(first["id"])).club == "Скала"
            assert before.get(Participant, uuid.UUID(second["id"])).club == "Горы"
        backups.append(kwargs)
        return {"filename": "test-merge.dump"}
    monkeypatch.setattr(backup_service, "create_backup", backup)
    return source, target, {
        "target_club_id": target["id"], "expected_version": source["version"],
        "target_expected_version": target["version"], "name_club_id": source["id"],
        "representative_club_id": target["id"], "source_member_ids": [first["id"]], "target_member_ids": [second["id"]],
    }, backups


def test_merge_mixed_choices_replay_and_archived_members(client, festival, auth_headers, merge_case):
    source, target, payload, backups = merge_case
    archived = create_participant(client, festival, auth_headers, "Архив", club="Скала", representative="Анна")
    with SessionLocal() as db:
        db.get(Participant, uuid.UUID(archived["id"])).archived_at = datetime.now(timezone.utc)
        db.commit()
    headers = command_headers(auth_headers)
    url = f"/api/v1/admin/clubs/{source['id']}/merge"
    result = client.post(url, headers=headers, json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["participant_count"] == 2
    assert result.json()["updated_participants"] == 3
    assert result.json()["name"] == "Скала"
    assert result.json()["representative"] == "Иван"
    assert len(backups) == 1
    assert backups[0]["note"] == "До объединения клубов «Скала» и «Горы»"
    assert client.post(url, headers=headers, json=payload).json() == result.json()
    assert len(backups) == 1
    with SessionLocal() as db:
        assert db.get(Club, uuid.UUID(source["id"])) is None
        members = db.scalars(select(Participant).where(Participant.club_id == uuid.UUID(target["id"]))).all()
        assert len(members) == 3
        assert all(p.club == "Скала" and p.representative == "Иван" for p in members)
        assert all(p.set_id == festival["first_set_id"] and not p.is_paid for p in members)


@pytest.mark.parametrize("role,expected", [(UserRole.secretary, 403), (UserRole.reception, 403), (UserRole.route_judge, 403), (UserRole.chief_judge, 200)])
def test_merge_role_boundary(client, festival, auth_headers, merge_case, role, expected):
    source, _, payload, backups = merge_case
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = role
        db.commit()
    response = client.post(f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert response.status_code == expected, response.text
    assert len(backups) == (1 if expected == 200 else 0)


@pytest.mark.parametrize("change", ["version", "members", "third_club", "same_club"])
def test_merge_rejects_stale_or_invalid_preview(client, festival, auth_headers, merge_case, change):
    source, target, payload, backups = merge_case
    if change == "version":
        payload["target_expected_version"] += 1
    elif change == "members":
        create_participant(client, festival, auth_headers, "Новый", club="Горы", representative="Иван")
    elif change == "third_club":
        create_participant(client, festival, auth_headers, "Третий", club="Скала", representative="Иван")
    else:
        payload["target_club_id"] = source["id"]
    response = client.post(f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert response.status_code in (409, 422), response.text
    assert not backups
    with SessionLocal() as db:
        assert db.get(Club, uuid.UUID(source["id"])) is not None
        assert db.get(Club, uuid.UUID(target["id"])) is not None


def test_backup_failure_leaves_clubs_unchanged(client, auth_headers, merge_case, monkeypatch):
    source, target, payload, _ = merge_case
    def fail(*args, **kwargs):
        raise backup_service.BackupError("disk full")
    monkeypatch.setattr(backup_service, "create_backup", fail)
    response = client.post(f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.get(Club, uuid.UUID(source["id"])).name == "Скала"
        assert db.get(Club, uuid.UUID(target["id"])).name == "Горы"
        assert db.get(Participant, uuid.UUID(payload["source_member_ids"][0])).club_id == uuid.UUID(source["id"])


def test_permissions_inherit_existing_denials_and_can_be_split(client, festival, auth_headers):
    with SessionLocal() as db:
        db.add_all([RolePermission(role=UserRole.chief_judge, permission="settings.manage", is_allowed=True),
                    RolePermission(role=UserRole.chief_judge, permission="clubs.manage", is_allowed=False)])
        db.commit()
        permissions = effective_permissions(db, UserRole.chief_judge)
        assert Permission.categories_manage in permissions
        assert Permission.clubs_merge not in permissions
    response = client.put("/api/v1/admin/roles/chief_judge/permissions", headers=command_headers(auth_headers),
                          json={"permissions": ["dashboard.view", "publication.manage"]})
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        permissions = effective_permissions(db, UserRole.chief_judge)
        assert Permission.publication_manage in permissions
        assert Permission.categories_manage not in permissions
        db.get(Admin, festival["admin_id"]).role = UserRole.chief_judge
        db.commit()
    assert client.get("/api/v1/admin/exports/settings", headers=auth_headers).status_code == 403
    assert client.get("/api/v1/admin/categories", headers=auth_headers).status_code == 403


def test_matrix_allows_merge_assignment_to_secretary(client, auth_headers):
    response = client.put("/api/v1/admin/roles/secretary/permissions", headers=command_headers(auth_headers),
                          json={"permissions": ["clubs.merge"]})
    assert response.status_code == 200
    matrix = client.get("/api/v1/admin/roles", headers=auth_headers).json()
    assert "restricted_roles" not in matrix
    assert "categories.manage" in matrix["available_permissions"]
    assert "settings.manage" not in matrix["available_permissions"]


def test_merge_creates_restorable_backup_of_original_clubs(client, auth_headers, merge_case, monkeypatch, tmp_path):
    source, target, payload, _ = merge_case
    monkeypatch.setattr(backup_service, "BACKUP_DIRECTORY", tmp_path)
    monkeypatch.setattr(backup_service, "create_backup", REAL_CREATE_BACKUP)
    response = client.post(f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers), json=payload)
    assert response.status_code == 200, response.text
    path = tmp_path / response.json()["backup_filename"]
    assert path.is_file()
    metadata = backup_service._read_metadata(path)
    assert metadata["verified_at"]
    assert metadata["summary"]["counts"]["clubs"] == 3  # fixture club plus the two originals
    database = f"climbhub_verify_{uuid.uuid4().hex[:12]}"
    try:
        backup_service._create_database(database)
        backup_service._restore_archive(path, database)
        with backup_service._psycopg_connection(database) as connection:
            rows = connection.execute("SELECT name, representative FROM clubs WHERE id IN (%s, %s) ORDER BY name", (source["id"], target["id"])).fetchall()
            assert rows == [("Горы", "Иван"), ("Скала", "Анна")]
            assert connection.execute("SELECT count(DISTINCT club_id) FROM participants").fetchone()[0] == 2
    finally:
        backup_service._drop_database(database)
        backup_service.delete_backup(path)


def test_merge_updates_final_displays_without_changing_snapshot(client, festival, auth_headers, merge_case):
    from app.models import Event, FinalRoute, QualificationResultSnapshot
    from app.routers.judge import workspace_response
    from test_stage8_judge import prepare_final
    _, target, _, _ = merge_case
    participant, routes = prepare_final(client, festival, auth_headers)
    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers).json()
    source = next(club for club in clubs if any(member["id"] == participant["id"] for member in club["members"]))
    with SessionLocal() as db:
        snapshot = db.scalar(select(QualificationResultSnapshot).where(QualificationResultSnapshot.participant_id == uuid.UUID(participant["id"])))
        frozen = (snapshot.club, snapshot.points, snapshot.place, snapshot.exit_order)
    response = client.post(f"/api/v1/admin/clubs/{source['id']}/merge", headers=command_headers(auth_headers), json={
        "target_club_id": target["id"], "expected_version": source["version"], "target_expected_version": target["version"],
        "name_club_id": target["id"], "representative_club_id": target["id"],
        "source_member_ids": [m["id"] for m in source["members"]], "target_member_ids": [m["id"] for m in target["members"]],
    })
    assert response.status_code == 200, response.text
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    group_id = next(category["id"] for category in status["categories"] if category["name"] == "Мужчины")
    for url in [f"/api/v1/admin/final/categories/{group_id}/results", f"/api/v1/admin/final/categories/{group_id}/final-results",
                "/api/v1/public/final-results?group=Мужчины", "/api/v1/public/absolute-results?stage=qualification"]:
        result = client.get(url, headers=auth_headers)
        assert result.status_code == 200, result.text
        row = next(row for row in result.json()["results"] if row["participant_id"] == participant["id"])
        assert row["club"] == target["name"]
    with SessionLocal() as db:
        snapshot = db.scalar(select(QualificationResultSnapshot).where(QualificationResultSnapshot.participant_id == uuid.UUID(participant["id"])))
        assert (snapshot.club, snapshot.points, snapshot.place, snapshot.exit_order) == frozen
        workspace = workspace_response(db, db.get(Event, festival["event_id"]), db.get(FinalRoute, uuid.UUID(routes[0]["id"])))
        assert next(row for row in workspace.participants if str(row.participant_id) == participant["id"]).club == target["name"]
