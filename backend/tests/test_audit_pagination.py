from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import AuditLog


def test_audit_pages_cover_all_rows_and_keep_filters(client, festival, auth_headers):
    with SessionLocal() as db:
        db.add_all(AuditLog(
            actor_email="pagination@test.local", actor_role="administrator",
            action="pagination.test", target_type="event", target_id=str(festival["event_id"]),
            result="success", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ) for _ in range(123))
        db.commit()
    pages = [client.get(
        f"/api/v1/admin/audit?action=pagination.test&actor=pagination&result=success&offset={offset}&limit=50",
        headers=auth_headers,
    ) for offset in (0, 50, 100)]
    assert all(response.status_code == 200 for response in pages)
    assert [len(response.json()["items"]) for response in pages] == [50, 50, 23]
    assert all(response.json()["total"] == 123 for response in pages)
    ids = [row["id"] for response in pages for row in response.json()["items"]]
    assert len(set(ids)) == 123
    assert ids == sorted(ids, reverse=True)
    empty = client.get("/api/v1/admin/audit?action=pagination.test&offset=123&limit=50", headers=auth_headers)
    assert empty.json() == {"items": [], "total": 123}
