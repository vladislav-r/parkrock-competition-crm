import re

from fastapi.routing import APIRoute
from app.main import app
from test_roles_and_audit import create_user, login_headers, operation_headers


def test_viewer_can_read_sections_but_cannot_mutate(client, festival, auth_headers):
    assert client.post('/api/v1/admin/roles', headers=operation_headers(auth_headers), json={'name': 'Просмотр'}).status_code == 201
    # Read-only must override accidentally selected write permissions too.
    assert client.put('/api/v1/admin/roles/Просмотр/permissions', headers=operation_headers(auth_headers), json={'permissions': ['system.read_only', 'users.manage', 'roles.manage']}).status_code == 200
    assert create_user(client, auth_headers, role='Просмотр').status_code == 201
    viewer = login_headers(client, 'reception@example.com')
    profile = client.get('/api/v1/auth/me', headers=viewer).json()
    assert 'system.read_only' in profile['permissions']
    assert 'users.manage' not in profile['permissions']
    for path in ['/event', '/participants', '/clubs', '/applications', '/final', '/categories', '/users', '/users/final-routes', '/roles', '/audit', '/exports/catalog', '/exports/settings', '/team-settings', '/competition/reset-status']:
        response = client.get('/api/v1/admin' + path, headers=viewer)
        assert response.status_code == 200, (path, response.text)
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(('/api/v1/admin', '/api/v1/judge')):
            continue
        for method in route.methods - {'GET', 'HEAD', 'OPTIONS'}:
            path = re.sub(r'\{[^}]+\}', '00000000-0000-0000-0000-000000000001', route.path)
            response = client.request(method, path, headers=operation_headers(viewer), json={})
            assert response.status_code == 403, (method, path, response.text)
            checked += 1
    assert checked > 40
    assert client.get('/api/v1/admin/backups/example.dump/download', headers=viewer).status_code == 403
    assert client.post('/api/v1/auth/logout', headers=viewer).status_code == 200
    # Administrator remains able to change data after the new restrictive flag.
    assert 'system.read_only' not in client.get('/api/v1/auth/me', headers=auth_headers).json()['permissions']
