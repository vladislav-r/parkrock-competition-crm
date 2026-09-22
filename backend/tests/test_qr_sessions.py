import base64
import hashlib
import hmac
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Admin, AuditLog, OperationRecord, UserAccess, UserRole
from app.security import create_access_token, decode_token_claims, hash_password
from app.sessions import credential_hash


def command(headers):
    return {**headers, "X-Operation-Id": str(uuid.uuid4())}


def staff(role=UserRole.reception):
    with SessionLocal() as db:
        user = Admin(email=f"{uuid.uuid4()}@qr.test", full_name="Тестовый сотрудник", password_hash=hash_password("password123"), role=role)
        db.add(user)
        db.commit()
        return str(user.id), user.email


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def password_login(client, email):
    result = client.post("/api/v1/auth/login", data={"username": email, "password": "password123"})
    assert result.status_code == 200, result.text
    return result.json()["access_token"]


def access(client, headers, user_id):
    return client.get("/api/v1/admin/users/access", headers=headers).json()[user_id]


def issue(client, headers, user_id, end=False):
    commands = command(headers)
    state = access(client, headers, user_id)
    payload = {"users": [{"user_id": user_id, "expected_version": state["version"]}], "origin": settings.cors_origins[0], "end_session": end}
    result = client.post("/api/v1/admin/users/qr/issue", json=payload, headers=commands)
    assert result.status_code == 200, result.text
    secret = hmac.new(settings.jwt_secret.encode(), f"parkrock-qr:{commands['X-Operation-Id']}:{user_id}".encode(), hashlib.sha256).digest()
    key = base64.urlsafe_b64encode(secret).decode().rstrip("=")
    return key, result, payload, commands


def qr_login(client, key):
    result = client.post("/api/v1/auth/qr/login", json={"key": key})
    assert result.status_code == 200, result.text
    return result.json()["access_token"]


def test_qr_and_password_replace_sessions(client, festival, auth_headers):
    uid, email = staff()
    first = password_login(client, email)
    key, result, payload, headers = issue(client, auth_headers, uid)
    assert result.headers["cache-control"] == "no-store"
    assert base64.b64decode(result.json()["pdf_base64"]).startswith(b"%PDF-")
    assert "<svg" in base64.b64decode(result.json()["cards"][0]["svg_base64"]).decode()
    assert client.post("/api/v1/admin/users/qr/issue", json=payload, headers=headers).status_code == 200
    # Scanning/preview must not terminate an existing session.
    assert client.post("/api/v1/auth/qr/preview", json={"key": key}).json()["full_name"] == "Тестовый сотрудник"
    assert client.get("/api/v1/auth/me", headers=bearer(first)).status_code == 200
    second = qr_login(client, key)
    old = client.get("/api/v1/auth/me", headers=bearer(first))
    assert old.status_code == 401 and "другом устройстве" in old.text
    claims = decode_token_claims(second)
    assert 43190 < claims["exp"] - datetime.now(timezone.utc).timestamp() <= 43200
    third = password_login(client, email)
    assert client.post("/api/v1/auth/logout", headers=bearer(second)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(third)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=bearer(third)).status_code == 200
    assert client.get("/api/v1/auth/heartbeat", headers=bearer(third)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(create_access_token(uid))).status_code == 401
    with SessionLocal() as db:
        assert db.get(UserAccess, uuid.UUID(uid)).qr_hash == credential_hash(key)
        serialized = json.dumps([row.response_json for row in db.scalars(select(OperationRecord))])
        serialized += json.dumps([row.new_value_json for row in db.scalars(select(AuditLog))])
        assert key not in serialized and second not in serialized


def test_settings_rotation_revoke_and_termination(client, festival, auth_headers):
    uid, _ = staff()
    key, _, old_payload, old_headers = issue(client, auth_headers, uid)
    token = qr_login(client, key)
    state = access(client, auth_headers, uid)
    payload = {"expected_version": state["version"], "qr_session_hours": 2}
    changed = client.put(f"/api/v1/admin/users/{uid}/qr/settings", headers=command(auth_headers), json=payload)
    assert changed.status_code == 200
    assert client.put(f"/api/v1/admin/users/{uid}/qr/settings", headers=command(auth_headers), json=payload).status_code == 409
    assert client.put(f"/api/v1/admin/users/{uid}/qr/settings", headers=command(auth_headers), json={**payload, "qr_session_hours": 0}).status_code == 422
    assert access(client, auth_headers, uid)["session_expires_at"] == state["session_expires_at"]
    short = qr_login(client, key)
    assert 7190 < decode_token_claims(short)["exp"] - datetime.now(timezone.utc).timestamp() <= 7200
    state = access(client, auth_headers, uid)
    commands = command(auth_headers)
    assert client.post(f"/api/v1/admin/users/{uid}/session/end", headers=commands, json={"session_id": state["session_id"]}).status_code == 200
    assert client.post(f"/api/v1/admin/users/{uid}/session/end", headers=commands, json={"session_id": state["session_id"]}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=bearer(short)).status_code == 401
    again = qr_login(client, key)
    assert client.get("/api/v1/auth/me", headers=bearer(again)).status_code == 200
    new_key, _, _, _ = issue(client, auth_headers, uid)
    assert client.post("/api/v1/auth/qr/login", json={"key": key}).status_code == 401
    assert client.post("/api/v1/admin/users/qr/issue", headers=old_headers, json=old_payload).status_code == 409
    assert client.get("/api/v1/auth/me", headers=bearer(again)).status_code == 200
    new_token = qr_login(client, new_key)
    state = access(client, auth_headers, uid)
    assert client.post(f"/api/v1/admin/users/{uid}/qr/revoke", headers=command(auth_headers), json={"expected_version": state["version"], "end_session": True}).status_code == 200
    assert client.post("/api/v1/auth/qr/login", json={"key": new_key}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(new_token)).status_code == 401


def test_permissions_disabled_expired_and_throttled(client, festival, auth_headers):
    uid, email = staff(UserRole.secretary)
    nonadmin = bearer(password_login(client, email))
    assert client.get("/api/v1/admin/users/access", headers=nonadmin).status_code == 403
    for path, payload in [("qr/revoke", {"expected_version": 1}), ("session/end", {"session_id": str(uuid.uuid4())})]:
        assert client.post(f"/api/v1/admin/users/{uid}/{path}", headers=command(nonadmin), json=payload).status_code == 403
    key, _, payload, _ = issue(client, auth_headers, uid)
    assert client.post("/api/v1/admin/users/qr/issue", headers=command(nonadmin), json=payload).status_code == 403
    assert client.post("/api/v1/admin/users/qr/issue", headers=command(auth_headers), json={**payload, "origin": "https://evil.test"}).status_code == 422
    token = qr_login(client, key)
    with SessionLocal() as db:
        db.get(UserAccess, uuid.UUID(uid)).session_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    with SessionLocal() as db:
        db.get(Admin, uuid.UUID(uid)).is_active = False
        db.commit()
    assert client.post("/api/v1/auth/qr/login", json={"key": key}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    for _ in range(35):
        last = client.post("/api/v1/auth/qr/preview", json={"key": "x" * 43})
    assert last.status_code == 429 and last.headers["retry-after"] == "60"


def test_concurrent_logins_leave_exactly_one_session(client, festival, auth_headers):
    uid, email = staff()
    key, _, _, _ = issue(client, auth_headers, uid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        passwords = pool.submit(password_login, client, email)
        qrs = pool.submit(qr_login, client, key)
        tokens = [passwords.result(), qrs.result()]
    assert sorted(client.get("/api/v1/auth/me", headers=bearer(token)).status_code for token in tokens) == [200, 401]


def test_revoke_without_logout_and_administrator_qr(client, festival, auth_headers):
    uid, _ = staff(UserRole.administrator)
    key, _, _, _ = issue(client, auth_headers, uid)
    token = qr_login(client, key)
    state = access(client, auth_headers, uid)
    result = client.post(f"/api/v1/admin/users/{uid}/qr/revoke", headers=command(auth_headers), json={"expected_version": state["version"]})
    assert result.status_code == 200
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    assert client.post("/api/v1/auth/qr/login", json={"key": key}).status_code == 401
    new_key, _, _, _ = issue(client, auth_headers, uid, end=True)
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    new_token = qr_login(client, new_key)
    self_headers = bearer(new_token)
    state = access(client, self_headers, uid)
    result = client.post(f"/api/v1/admin/users/{uid}/session/end", headers=command(self_headers), json={"session_id": state["session_id"]})
    assert result.status_code == 200
    assert client.get("/api/v1/auth/me", headers=self_headers).status_code == 401
