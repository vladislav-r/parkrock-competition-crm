import uuid
from datetime import date
from io import BytesIO
from datetime import datetime, timezone

from openpyxl import Workbook
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ApplicationType, CompetitionSet, Event, Participant, ParticipantSource
from app.services import age_on


def command_headers(auth_headers):
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def upload(client, auth_headers, content: str, query: str):
    return client.post(
        f"/api/v1/admin/participants/import?{query}", headers=command_headers(auth_headers),
        files={"file": ("participants.csv", content.encode("utf-8"), "text/csv")},
    )


def test_import_preview_marks_cells_and_can_skip_duplicates(client, festival, auth_headers):
    invalid = (
        "Фамилия;Имя;Отчество;Дата рождения;Пол;Разряд;Клуб;Сет;Представитель;Мерч\n"
        "Петров;Петр;Петрович;01.02.1995;Мужской;Без разряда;Высота;Сет 1;Сидоров;L\n"
        "Сидорова;Анна;;не дата;Женский;1 взрослый;Высота;Сет 1;;;\n"
    )
    preview = upload(client, auth_headers, invalid, "preview=true&application_type=collective")
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    assert preview.json()["error_rows"] == 1
    assert "Дата рождения" in preview.json()["rows"][1]["errors"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Participant)) == 0

    valid = invalid.splitlines()[0] + "\n" + invalid.splitlines()[1] + "\n"
    imported = upload(client, auth_headers, valid, "application_type=collective")
    assert imported.status_code == 200, imported.text
    duplicate_and_new = valid + "Иванова;Мария;;03.04.1998;Женский;Без разряда;Высота;Сет 1;;M\n"
    duplicate_preview = upload(client, auth_headers, duplicate_and_new, "preview=true&application_type=collective")
    assert duplicate_preview.json()["duplicate_rows"] == 1
    assert duplicate_preview.json()["valid_rows"] == 1
    accepted = upload(client, auth_headers, duplicate_and_new, "application_type=collective&skip_duplicates=true")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["imported"] == 1
    assert accepted.json()["skipped_duplicates"] == 1
    with SessionLocal() as db:
        participants = list(db.scalars(select(Participant).order_by(Participant.start_number)).all())
        assert [item.start_number for item in participants] == [1, 2]
        assert participants[0].application_type == ApplicationType.collective
        assert participants[0].source == ParticipantSource.import_file
        assert participants[0].merch_size is None


def test_festival_application_template_imports_team_and_birth_year(client, festival, auth_headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A4"] = "Название команды:"
    sheet["E4"] = "Высота"
    sheet["A5"] = "Представителем команды назначается:"
    sheet["E5"] = "Иванов Иван Иванович"
    sheet["A6"] = "Телефон:"
    sheet["E6"] = "79998887766"
    sheet.append([])
    sheet.append([])
    sheet.append(["№ п/п", "Фамилия ", "Имя", "Отчество (можно оставить пустым)", "Год рождения", "Пол", "Разряд", "Сет", "Футболка (размер или оставить пустым)"])
    sheet.append([1, "Петров", "Петр", None, "2013", "М", "2 юношеский", 1, "M"])
    content = BytesIO()
    workbook.save(content)

    preview = client.post(
        "/api/v1/admin/participants/import?preview=true&application_type=collective",
        headers=command_headers(auth_headers),
        files={"file": ("Заявка.xlsx", content.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    assert preview.json()["rows"][0]["values"]["Год рождения"] == "2013"
    assert "Футболка" not in preview.json()["rows"][0]["values"]

    imported = client.post(
        "/api/v1/admin/participants/import?application_type=collective",
        headers=command_headers(auth_headers),
        files={"file": ("Заявка.xlsx", content.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert imported.status_code == 200, imported.text
    with SessionLocal() as db:
        participant = db.scalar(select(Participant))
        assert participant.club == "Высота"
        assert participant.representative == "Иванов Иван Иванович"
        assert participant.birth_date == date(2013, 1, 1)
        assert participant.birth_year == 2013
        assert participant.merch_size is None
    assert age_on(date(2013, 12, 31), date(2026, 1, 1)) == 13


def test_manual_and_imported_participant_age_must_be_between_zero_and_99(client, festival, auth_headers):
    with SessionLocal() as db:
        event_year = db.get(Event, festival["event_id"]).starts_on.year

    base = {
        "set_id": str(festival["first_set_id"]), "surname": "Возраст", "name": "Проверка",
        "sex": "female", "sport_rank": "Без разряда", "club": "Возрастной клуб",
        "representative": "", "merch_size": None,
    }
    future = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={**base, "birth_date": f"{event_year + 1}-01-01"},
    )
    assert future.status_code == 422, future.text
    assert future.json()["detail"]["code"] == "invalid_age"
    assert "отрицательным" in future.json()["detail"]["message"]

    too_old = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={**base, "birth_date": f"{event_year - 100}-01-01"},
    )
    assert too_old.status_code == 422, too_old.text
    assert "99" in too_old.json()["detail"]["message"]

    csv = (
        "Фамилия;Имя;Отчество;Дата рождения;Пол;Разряд;Клуб;Сет;Представитель;Мерч\n"
        f"Будущий;Участник;;01.01.{event_year + 1};Мужской;Без разряда;Клуб;Сет 1;;;\n"
        f"Старший;Участник;;01.01.{event_year - 100};Мужской;Без разряда;Клуб;Сет 1;;;\n"
    )
    preview = upload(client, auth_headers, csv, "preview=true&application_type=collective")
    assert preview.status_code == 200, preview.text
    assert preview.json()["error_rows"] == 2
    assert "отрицательным" in preview.json()["rows"][0]["errors"]["Дата рождения"]
    assert "99" in preview.json()["rows"][1]["errors"]["Дата рождения"]


def test_festival_application_template_requires_representative(client, festival, auth_headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A4"] = "Название команды:"
    sheet["E4"] = "Высота"
    sheet["A5"] = "Представителем команды назначается:"
    sheet.append([])
    sheet.append([])
    sheet.append([])
    sheet.append(["№ п/п", "Фамилия", "Имя", "Отчество", "Год рождения", "Пол", "Разряд", "Сет"])
    sheet.append([1, "Петров", "Петр", None, 2013, "М", "2 юношеский", 1])
    content = BytesIO()
    workbook.save(content)

    response = client.post(
        "/api/v1/admin/participants/import?preview=true&application_type=collective",
        headers=command_headers(auth_headers),
        files={"file": ("Заявка.xlsx", content.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 422
    assert "Представителем команды" in response.json()["detail"]


def test_manual_participant_gets_nearby_number_and_final_blocks_creation(client, festival, auth_headers):
    first = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Орлова", "name": "Ирина",
            "patronymic": "", "birth_date": "1994-05-06", "sex": "female",
            "sport_rank": "Без разряда", "club": "Онсайт", "representative": "", "merch_size": "S",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["application_type"] == "individual"
    assert first.json()["source"] == "manual"
    assert first.json()["start_number"] == 1

    second = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "Орлов", "name": "Павел",
            "patronymic": "", "birth_date": "1993-04-05", "sex": "male",
            "sport_rank": "Без разряда", "club": "Онсайт", "representative": "", "merch_size": None,
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["start_number"] == 2

    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.final_started_at = datetime.now(timezone.utc)
        db.commit()
    blocked = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={
            "set_id": str(festival["first_set_id"]), "surname": "После", "name": "Финала",
            "birth_date": "1990-01-01", "sex": "male", "sport_rank": "Без разряда", "club": "Клуб",
        },
    )
    assert blocked.status_code == 409
    assert "запуска финала" in blocked.json()["detail"]


def test_manual_participant_can_confirm_set_overflow(client, festival, auth_headers):
    with SessionLocal() as db:
        competition_set = db.get(CompetitionSet, festival["first_set_id"])
        competition_set.capacity = 1
        db.commit()

    base = {
        "set_id": str(festival["first_set_id"]), "patronymic": "", "birth_date": "1994-05-06",
        "sex": "female", "sport_rank": "Без разряда", "club": "Онсайт",
        "representative": "", "merch_size": None,
    }
    first = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={**base, "surname": "Первая", "name": "Участница"},
    )
    assert first.status_code == 201, first.text

    blocked = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={**base, "surname": "Вторая", "name": "Участница"},
    )
    assert blocked.status_code == 409
    assert "Подтвердите" in blocked.json()["detail"]

    confirmed = client.post(
        "/api/v1/admin/participants", headers=command_headers(auth_headers),
        json={**base, "surname": "Вторая", "name": "Участница", "allow_overflow": True},
    )
    assert confirmed.status_code == 201, confirmed.text
    with SessionLocal() as db:
        count = db.scalar(select(func.count()).select_from(Participant).where(
            Participant.set_id == festival["first_set_id"], Participant.archived_at.is_(None)))
        assert count == 2
