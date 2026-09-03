from app import backup_service
from app.db import SessionLocal
from app.models import Admin, UserRole


def test_backups_are_available_only_to_administrator(client, festival, auth_headers, monkeypatch):
    monkeypatch.setattr(backup_service, "list_backups", lambda db: {"items": [], "current": {"counts": {}}, "directory": "backups"})
    response = client.get("/api/v1/admin/backups", headers=auth_headers)
    assert response.status_code == 200

    db = SessionLocal()
    try:
        admin = db.get(Admin, festival["admin_id"])
        admin.role = UserRole.secretary
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/admin/backups", headers=auth_headers)
    assert response.status_code == 403


def test_backup_delete_requires_exact_confirmation(client, auth_headers):
    response = client.request(
        "DELETE", "/api/v1/admin/backups/example.dump", headers=auth_headers,
        json={"confirmation": "удалить"},
    )
    assert response.status_code == 422
    assert "УДАЛИТЬ" in response.json()["detail"]


def test_backup_filename_cannot_escape_directory():
    try:
        backup_service.resolve_backup("../database.dump")
    except backup_service.BackupError as error:
        assert "имя" in str(error).lower()
    else:
        raise AssertionError("Path traversal must be rejected")
