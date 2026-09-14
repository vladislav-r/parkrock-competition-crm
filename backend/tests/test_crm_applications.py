import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Admin, ApplicationFile, AuditLog, Event, Participant, RolePermission, UserRole
from test_applications import application_xlsx


def test_crm_upload_only_stores_file_and_reuses_public_validation(client, festival, auth_headers):
    content = application_xlsx()
    files = {"file": ("Заявка.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    public = client.post("/api/v1/public/applications", files=files)
    assert public.status_code == 201
    repeated = client.post("/api/v1/admin/applications", headers=auth_headers, files=files)
    assert repeated.status_code == 201 and repeated.json()["id"] == public.json()["id"]
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).is_public = False
        db.commit()
    new_content = application_xlsx(surname="Новая")
    uploaded = client.post("/api/v1/admin/applications", headers=auth_headers, files={"file": ("Новая.xlsx", new_content)})
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["status"] == "pending"
    assert client.get(f"/api/v1/admin/applications/{uploaded.json()['id']}/download", headers=auth_headers).content == new_content
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 0
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 2
        assert db.scalar(select(AuditLog).where(AuditLog.action == "application.upload")) is not None


@pytest.mark.parametrize("filename,content,status", [("bad.csv", b"abc", 422), ("empty.xlsx", b"", 422), ("broken.xlsx", b"broken", 422), ("large.xlsx", b"x" * (10 * 1024 * 1024 + 1), 413), ("invalid.xlsx", application_xlsx(sex="invalid"), 422)], ids=["extension", "empty", "broken", "oversized", "invalid-row"])
def test_crm_upload_rejects_invalid_files(client, festival, auth_headers, filename, content, status):
    files = {"file": (filename, content)}
    public = client.post("/api/v1/public/applications", files=files)
    crm = client.post("/api/v1/admin/applications", headers=auth_headers, files=files)
    assert crm.status_code == public.status_code == status
    assert crm.json() == public.json()


def test_crm_upload_requires_import_permission(client, festival, auth_headers):
    with SessionLocal() as db:
        db.get(Admin, festival["admin_id"]).role = UserRole.reception
        db.add(RolePermission(role=UserRole.reception, permission="participants.import", is_allowed=False))
        db.commit()
    files = {"file": ("Заявка.xlsx", application_xlsx())}
    assert client.post("/api/v1/admin/applications", files=files).status_code == 401
    assert client.post("/api/v1/admin/applications", files=files, headers=auth_headers).status_code == 403
