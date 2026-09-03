import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Ascent, Club, CompetitionSet, Participant, Route, SetStatus, Sex


def command_headers(auth_headers, operation_id=None):
    return {**auth_headers, "X-Operation-Id": str(operation_id or uuid.uuid4())}


def add_participant(*, event_id, set_id, start_number, checked_in=False, surname="Иванов"):
    db = SessionLocal()
    try:
        club = db.scalar(select(Club).where(Club.event_id == event_id))
        participant = Participant(
            event_id=event_id,
            club_id=club.id,
            set_id=set_id,
            start_number=start_number,
            surname=surname,
            name="Иван",
            patronymic="Иванович",
            birth_date=date(1990, 1, 1),
            sex=Sex.male,
            sport_rank="Без разряда",
            club="Тестовый клуб",
            representative="",
            checked_in_at=datetime.now(timezone.utc) if checked_in else None,
        )
        db.add(participant)
        db.commit()
        return participant.id
    finally:
        db.close()


def test_admin_api_requires_authentication(client, festival):
    response = client.get("/api/v1/admin/event")
    assert response.status_code == 401


def test_import_and_duplicate_rejection(client, festival, auth_headers):
    content = (
        "Фамилия;Имя;Отчество;Дата рождения;Пол;Разряд;Клуб;Сет;Представитель\n"
        "Петров;Петр;Петрович;01.02.1995;Мужской;Без разряда;Высота;Сет 1;Сидоров С.С.\n"
    ).encode("utf-8")
    response = client.post(
        "/api/v1/admin/participants/import",
        headers=command_headers(auth_headers),
        files={"file": ("participants.csv", content, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["imported"] == 1

    duplicate = client.post(
        "/api/v1/admin/participants/import",
        headers=command_headers(auth_headers),
        files={"file": ("participants.csv", content, "text/csv")},
    )
    assert duplicate.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 1


def test_check_in_is_idempotent(client, festival, auth_headers):
    participant_id = add_participant(
        event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=101
    )
    operation_id = uuid.uuid4()
    headers = command_headers(auth_headers, operation_id)
    first = client.post(f"/api/v1/admin/participants/{participant_id}/check-in", headers=headers, json={"expected_version": 1})
    second = client.post(f"/api/v1/admin/participants/{participant_id}/check-in", headers=headers, json={"expected_version": 1})
    assert first.status_code == second.status_code == 200
    assert first.json()["checked_in_at"] == second.json()["checked_in_at"]


def test_stale_participant_version_is_rejected(client, festival, auth_headers):
    participant_id = add_participant(
        event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=101, checked_in=True
    )
    first = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(festival["route_ids"][0])], "expected_version": 1},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    stale = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(festival["route_ids"][1])], "expected_version": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "edit_conflict"
    with SessionLocal() as db:
        completed = db.scalars(select(Ascent).where(
            Ascent.participant_id == participant_id, Ascent.is_completed.is_(True)
        )).all()
        assert [item.route_id for item in completed] == [festival["route_ids"][0]]


def test_route_update_is_replayable_and_versioned(client, festival, auth_headers):
    route_id = festival["route_ids"][0]
    operation_id = uuid.uuid4()
    headers = command_headers(auth_headers, operation_id)
    payload = {"name": "Обновленная трасса", "expected_version": 1}

    first = client.patch(f"/api/v1/admin/routes/{route_id}", headers=headers, json=payload)
    replay = client.patch(f"/api/v1/admin/routes/{route_id}", headers=headers, json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["version"] == 2

    stale = client.patch(
        f"/api/v1/admin/routes/{route_id}",
        headers=command_headers(auth_headers),
        json={"name": "Устаревшее изменение", "expected_version": 1},
    )
    assert stale.status_code == 409
    with SessionLocal() as db:
        assert db.get(Route, route_id).name == "Обновленная трасса"


def test_set_update_is_replayable_and_versioned(client, festival, auth_headers):
    set_id = festival["first_set_id"]
    operation_id = uuid.uuid4()
    headers = command_headers(auth_headers, operation_id)
    payload = {
        "name": "Обновленный сет", "start_time": "09:30:00", "end_time": "12:30:00",
        "capacity": 20, "expected_version": 1,
    }

    first = client.patch(f"/api/v1/admin/sets/{set_id}", headers=headers, json=payload)
    replay = client.patch(f"/api/v1/admin/sets/{set_id}", headers=headers, json=payload)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["version"] == 2
    assert first.json()["time_label"] == "09:30-12:30"

    stale = client.patch(
        f"/api/v1/admin/sets/{set_id}",
        headers=command_headers(auth_headers),
        json={**payload, "name": "Устаревший сет", "expected_version": 1},
    )
    assert stale.status_code == 409


def test_move_participant_checks_capacity(client, festival, auth_headers):
    participant_id = add_participant(
        event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=101
    )
    add_participant(
        event_id=festival["event_id"], set_id=festival["second_set_id"], start_number=102, surname="Сидоров"
    )
    with SessionLocal() as db:
        target = db.get(CompetitionSet, festival["second_set_id"])
        target.capacity = 1
        db.commit()

    response = client.patch(
        f"/api/v1/admin/participants/{participant_id}/set",
        headers=command_headers(auth_headers),
        json={"set_id": str(festival["second_set_id"]), "expected_version": 1},
    )
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.get(Participant, participant_id).set_id == festival["first_set_id"]


def test_batch_results_are_atomic_and_set_lock_is_enforced(client, festival, auth_headers):
    participant_id = add_participant(
        event_id=festival["event_id"], set_id=festival["first_set_id"], start_number=101, checked_in=True
    )
    first_route = festival["route_ids"][0]
    response = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(first_route)], "expected_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["completed_count"] == 1

    invalid = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [str(uuid.uuid4())], "expected_version": 2},
    )
    assert invalid.status_code == 422
    with SessionLocal() as db:
        completed = db.scalars(select(Ascent).where(
            Ascent.participant_id == participant_id, Ascent.is_completed.is_(True)
        )).all()
        assert [item.route_id for item in completed] == [first_route]

    confirmed = client.post(
        f"/api/v1/admin/sets/{festival['first_set_id']}/confirm",
        headers=command_headers(auth_headers), json={"expected_version": 1},
    )
    assert confirmed.status_code == 200
    blocked = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [], "expected_version": 2},
    )
    assert blocked.status_code == 409
    reopened = client.post(
        f"/api/v1/admin/sets/{festival['first_set_id']}/reopen",
        headers=command_headers(auth_headers), json={"expected_version": 2},
    )
    assert reopened.status_code == 200
    allowed = client.put(
        f"/api/v1/admin/participants/{participant_id}/results",
        headers=command_headers(auth_headers),
        json={"completed_route_ids": [], "expected_version": 2},
    )
    assert allowed.status_code == 200


def test_public_ranking_includes_ties_at_finalist_boundary(client, festival):
    db = SessionLocal()
    try:
        db.query(Route).filter(Route.event_id == festival["event_id"]).delete()
        routes = [
            Route(
                event_id=festival["event_id"], number=index, name=f"Трасса {index}",
                grade="6A", points=1100 - index * 100, sort_order=index, is_active=True,
            )
            for index in range(1, 11)
        ]
        db.add_all(routes)
        db.flush()
        for index in range(1, 12):
            participant = Participant(
                event_id=festival["event_id"], club_id=festival["club_id"], set_id=festival["first_set_id"], start_number=100 + index,
                surname=f"Участник{index:02}", name="Тест", patronymic="", birth_date=date(1990, 1, 1),
                sex=Sex.male, sport_rank="Без разряда", club="Клуб", representative="",
                checked_in_at=datetime.now(timezone.utc),
            )
            db.add(participant)
            db.flush()
            route = routes[min(index, 10) - 1]
            db.add(Ascent(participant_id=participant.id, route_id=route.id, is_completed=True))
        db.commit()
    finally:
        db.close()

    response = client.get("/api/v1/public/results", params={"group": "Мужчины"})
    assert response.status_code == 200
    ranked = [row for row in response.json()["results"] if row["has_result"]]
    assert len(ranked) == 11
    assert ranked[9]["place"] == ranked[10]["place"] == 10
    assert ranked[9]["is_finalist"] is True
    assert ranked[10]["is_finalist"] is True
