"""Targeted production acceptance of application intake and participant import."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier, BrokenBarrierError

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ApplicationFile, CompetitionSet, Participant, SetStatus
from test_applications import application_xlsx, operation_headers


def submit(client, content):
    return client.post('/api/v1/public/applications', files={'file': ('Заявка.xlsx', content)})


def with_second_row(content, surname):
    workbook = load_workbook(BytesIO(content))
    sheet = workbook['Лист1']
    sheet.append([2, surname, 'Иван', None, 2013, 'М', 'б/р', '1 (08:00–10:30)'])
    result = BytesIO()
    workbook.save(result)
    workbook.close()
    return result.getvalue()


def test_direct_import_replays_success(client, festival, auth_headers):
    headers = operation_headers(auth_headers)
    content = application_xlsx()
    def send():
        return client.post('/api/v1/admin/participants/import', headers=headers,
                           files={'file': ('Заявка.xlsx', content)})
    first = send()
    assert first.status_code == 200, first.text
    repeated = send()
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == first.json()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 1


def test_unrelated_overflow_does_not_block_application(client, festival, auth_headers):
    first = submit(client, application_xlsx()).json()['id']
    assert client.post(f'/api/v1/admin/applications/{first}/import',
                       headers=operation_headers(auth_headers)).status_code == 200
    extra = submit(client, application_xlsx(surname='Третий')).json()['id']
    assert client.post(f'/api/v1/admin/applications/{extra}/import',
                       headers=operation_headers(auth_headers)).status_code == 200
    with SessionLocal() as db:
        db.get(CompetitionSet, festival['first_set_id']).capacity = 1
        db.commit()
    second = submit(client, application_xlsx(surname='Другой', competition_set='2 (10:45–13:15)'))
    assert second.status_code == 201, second.text
    imported = client.post(f"/api/v1/admin/applications/{second.json()['id']}/import",
                           headers=operation_headers(auth_headers))
    assert imported.status_code == 200, imported.text


@pytest.mark.parametrize('same_person', [True, False])
def test_parallel_applications_recheck_duplicates_and_capacity(client, festival, auth_headers, monkeypatch, same_person):
    import app.routers.applications as routes
    with SessionLocal() as db:
        db.get(CompetitionSet, festival['first_set_id']).capacity = 1
        db.commit()
    ids = [submit(client, application_xlsx(surname=surname, phone=phone)).json()['id']
           for surname, phone in [('Петров', '79999999999'),
                                  ('Петров' if same_person else 'Сидоров', '79999999998')]]
    original = routes.analyze
    barrier = Barrier(2)
    def synchronized_analysis(*args, **kwargs):
        result = original(*args, **kwargs)
        try:
            barrier.wait(timeout=1)
        except BrokenBarrierError:
            pass
        return result
    monkeypatch.setattr(routes, 'analyze', synchronized_analysis)
    def import_one(application_id):
        return client.post(f'/api/v1/admin/applications/{application_id}/import',
                           headers=operation_headers(auth_headers))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(import_one, ids))
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()['detail']['code'] == ('duplicate_participants' if same_person else 'set_capacity_overflow')
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 1
        assert sorted(db.scalars(select(ApplicationFile.status)).all()) == ['imported', 'pending']


@pytest.mark.parametrize('content,filename,status', [(b'', 'empty.xlsx', 422), (b'bad', 'bad.xlsx', 422),
    (b'bad', 'bad.pdf', 422), (b'x' * (10 * 1024 * 1024 + 1), 'large.xlsx', 413)],
    ids=['empty', 'corrupt', 'extension', 'oversized'])
def test_invalid_upload_creates_nothing(client, festival, content, filename, status):
    response = client.post('/api/v1/public/applications', files={'file': (filename, content)})
    assert response.status_code == status, response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 0
        assert db.scalar(select(func.count()).select_from(Participant)) == 0


def test_saved_import_replay_and_participant_visibility(client, festival, auth_headers):
    application = submit(client, application_xlsx()).json()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 0
    headers = operation_headers(auth_headers)
    url = f"/api/v1/admin/applications/{application['id']}/import"
    first = client.post(url, headers=headers)
    assert first.status_code == 200, first.text
    repeated = client.post(url, headers=headers)
    assert repeated.status_code == 200, repeated.text
    assert first.json() == repeated.json()
    participants = client.get('/api/v1/admin/participants', headers=auth_headers)
    assert participants.status_code == 200, participants.text
    assert len(participants.json()) == 1
    participant = participants.json()[0]
    assert participant['surname'] == 'Петров'
    assert participant['birth_year'] == 2013
    assert participant['set_id'] == str(festival['first_set_id'])
    assert participant['club'] == 'Высота'
    assert participant['application_type'] == 'collective'


def test_partial_invalid_application_is_atomic(client, festival):
    response = submit(client, with_second_row(application_xlsx(), None))
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert detail['valid_rows'] == 1
    assert detail['error_rows'] == 1
    assert 'Фамилия' in detail['rows'][1]['errors']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 0
        assert db.scalar(select(func.count()).select_from(Participant)) == 0


def test_import_rechecks_set_closed_after_submission(client, festival, auth_headers):
    item = submit(client, application_xlsx()).json()
    with SessionLocal() as db:
        db.get(CompetitionSet, festival['first_set_id']).status = SetStatus.confirmed
        db.commit()
    response = client.post(f"/api/v1/admin/applications/{item['id']}/import",
                           headers=operation_headers(auth_headers))
    assert response.status_code == 422, response.text
    assert 'Сет' in response.json()['detail']['rows'][0]['errors']
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 0
        assert db.scalar(select(ApplicationFile.status)) == 'pending'


def test_duplicates_and_overflow_need_separate_confirmation(client, festival, auth_headers):
    first = submit(client, application_xlsx()).json()
    assert client.post(f"/api/v1/admin/applications/{first['id']}/import",
                       headers=operation_headers(auth_headers)).status_code == 200
    second = submit(client, with_second_row(application_xlsx(), 'Сидоров')).json()
    with SessionLocal() as db:
        db.get(CompetitionSet, festival['first_set_id']).capacity = 1
        db.commit()
    url = f"/api/v1/admin/applications/{second['id']}/import"
    duplicate = client.post(url, headers=operation_headers(auth_headers))
    assert duplicate.status_code == 409
    assert duplicate.json()['detail']['code'] == 'duplicate_participants'
    overflow = client.post(url + '?skip_duplicates=true', headers=operation_headers(auth_headers))
    assert overflow.status_code == 409
    assert overflow.json()['detail']['code'] == 'set_capacity_overflow'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 1
    success = client.post(url + '?skip_duplicates=true&allow_overflow=true', headers=operation_headers(auth_headers))
    assert success.status_code == 200, success.text
    assert success.json()['imported'] == 1
    assert success.json()['skipped_duplicates'] == 1
    with SessionLocal() as db:
        assert list(db.scalars(select(Participant.start_number).order_by(Participant.start_number))) == [1, 2]


def test_anonymous_user_cannot_process_application(client, festival):
    item = submit(client, application_xlsx()).json()
    base = f"/api/v1/admin/applications/{item['id']}"
    for response in [client.get('/api/v1/admin/applications'), client.get(base + '/download'),
                     client.post(base + '/import'), client.delete(base)]:
        assert response.status_code == 401, response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 1
        assert db.scalar(select(func.count()).select_from(Participant)) == 0


def test_manual_application_cannot_duplicate_imported_participant(client, festival, auth_headers):
    item = submit(client, application_xlsx()).json()
    assert client.post(f"/api/v1/admin/applications/{item['id']}/import",
                       headers=operation_headers(auth_headers)).status_code == 200
    response = client.post('/api/v1/admin/participants', headers=operation_headers(auth_headers), json={
        'set_id': str(festival['first_set_id']), 'surname': ' ПЕТРОВ ', 'name': 'Петр',
        'patronymic': '', 'birth_date': '2013-05-06', 'sex': 'male', 'sport_rank': 'б/р', 'club': 'Высота',
    })
    assert response.status_code == 409, response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 1


def test_notification_outage_does_not_lose_application(client, festival, auth_headers, monkeypatch):
    import app.telegram as telegram
    import httpx
    monkeypatch.setattr(telegram, 'telegram_delivery_enabled', lambda: True)
    class OfflineClient:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            raise httpx.ConnectError('simulated notification outage')
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(telegram.httpx, 'AsyncClient', OfflineClient)
    content = application_xlsx()
    response = submit(client, content)
    assert response.status_code == 201, response.text
    downloaded = client.get(f"/api/v1/admin/applications/{response.json()['id']}/download", headers=auth_headers)
    assert downloaded.status_code == 200
    assert downloaded.content == content
