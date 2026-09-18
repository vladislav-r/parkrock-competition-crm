from datetime import timedelta

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Admin, UserPresence
from test_roles_and_audit import create_user, login_headers, operation_headers


def test_presence_transitions_validation_and_user_versions(client, festival, auth_headers):
    user_id = str(festival["admin_id"])
    def presence():
        return client.get('/api/v1/admin/users/presence', headers=auth_headers).json()[user_id]
    assert presence()['status'] == 'offline'
    assert presence()['last_seen'] is None
    assert client.post('/api/v1/auth/heartbeat', json={'latency_ms': 85}).status_code == 401
    for latency in [-1, 60001]:
        assert client.post('/api/v1/auth/heartbeat', headers=auth_headers, json={'latency_ms': latency}).status_code == 422
    with SessionLocal() as db:
        version = db.get(Admin, festival['admin_id']).version
    for latency, unstable, expected in [(85, False, 'online'), (1200, False, 'unstable'), (85, True, 'unstable'), (40, False, 'online')]:
        assert client.post('/api/v1/auth/heartbeat', headers=auth_headers, json={'latency_ms': latency, 'unstable': unstable}).status_code == 200
        assert presence()['status'] == expected
        assert presence()['latency_ms'] == latency
    for seconds, expected in [(30, 'unstable'), (95, 'offline')]:
        with SessionLocal() as db:
            db.get(UserPresence, festival['admin_id']).last_seen = db.scalar(select(func.now())) - timedelta(seconds=seconds)
            db.commit()
        assert presence()['status'] == expected
    with SessionLocal() as db:
        assert db.get(Admin, festival['admin_id']).version == version
    assert client.post('/api/v1/auth/heartbeat', headers=auth_headers, json={'latency_ms': 55}).status_code == 200
    assert presence()['status'] == 'online'


def test_presence_all_roles_and_read_only(client, festival, auth_headers):
    for role in ['reception', 'secretary', 'chief_judge', 'route_judge']:
        email = f'{role}@example.com'
        created = create_user(client, auth_headers, role=role, email=email,
                              route_id=festival['route_ids'][0] if role == 'route_judge' else None)
        assert created.status_code == 201, created.text
        headers = login_headers(client, email)
        assert client.get('/api/v1/auth/heartbeat', headers=headers).status_code == 200
        assert client.post('/api/v1/auth/heartbeat', headers=headers, json={'latency_ms': 25}).status_code == 200
    receptionist = login_headers(client, 'reception@example.com')
    assert client.get('/api/v1/admin/users/presence', headers=receptionist).status_code == 403
    assert client.post('/api/v1/admin/roles', headers=operation_headers(auth_headers), json={'name': 'Просмотр'}).status_code == 201
    assert client.put('/api/v1/admin/roles/Просмотр/permissions', headers=operation_headers(auth_headers), json={'permissions': ['system.read_only']}).status_code == 200
    assert create_user(client, auth_headers, role='Просмотр', email='viewer@example.com').status_code == 201
    viewer = login_headers(client, 'viewer@example.com')
    assert client.post('/api/v1/auth/heartbeat', headers=viewer, json={'latency_ms': 100}).status_code == 200
    assert client.get('/api/v1/admin/users/presence', headers=viewer).status_code == 403
    assert client.put('/api/v1/admin/roles/Просмотр/permissions', headers=operation_headers(auth_headers), json={'permissions': ['system.read_only', 'users.presence']}).status_code == 200
    assert 'users.presence' in client.get('/api/v1/auth/me', headers=viewer).json()['permissions']
    assert client.get('/api/v1/admin/users/presence', headers=viewer).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(Admin).where(Admin.email == 'viewer@example.com'))
        user.is_active = False
        user_id = str(user.id)
        db.commit()
    assert client.post('/api/v1/auth/heartbeat', headers=viewer, json={'latency_ms': 100}).status_code == 401
    assert client.get('/api/v1/admin/users/presence', headers=auth_headers).json()[user_id]['status'] == 'offline'


def test_presence_permission_is_independent_and_preserves_legacy_grants(client, festival, auth_headers):
    from app.models import RolePermission

    assert create_user(client, auth_headers, role='reception').status_code == 201
    staff = login_headers(client, 'reception@example.com')
    path = '/api/v1/admin/roles/reception/permissions'
    assert client.put(path, headers=operation_headers(auth_headers), json={'permissions': ['users.presence']}).status_code == 200
    response = client.get('/api/v1/admin/users/presence', headers=staff)
    assert response.status_code == 200
    assert response.json()[str(festival['admin_id'])]['full_name']
    assert 'email' not in response.json()[str(festival['admin_id'])]
    assert client.get('/api/v1/admin/users', headers=staff).status_code == 403
    assert client.put(path, headers=operation_headers(auth_headers), json={'permissions': ['users.manage']}).status_code == 200
    assert client.get('/api/v1/admin/users/presence', headers=staff).status_code == 403
    with SessionLocal() as db:
        db.delete(db.scalar(select(RolePermission).where(RolePermission.role == 'reception', RolePermission.permission == 'users.presence')))
        db.commit()
    assert client.get('/api/v1/admin/users/presence', headers=staff).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(Admin).where(Admin.email == 'reception@example.com'))
        user.role = 'Оператор'
        db.add(RolePermission(role='Оператор', permission='users.manage', is_allowed=True))
        db.commit()
    assert client.get('/api/v1/admin/users/presence', headers=staff).status_code == 200
