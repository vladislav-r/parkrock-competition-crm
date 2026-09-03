import uuid
from datetime import datetime, timezone
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ApplicationFile, Club, Event, Participant


def application_xlsx(
    surname: str = "Петров", shirt_size: str | None = "S",
    team_name: str = "Высота", representative: str = "Иванов Иван Иванович",
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A4"] = "Название команды:"
    sheet["E4"] = team_name
    sheet["A5"] = "Представителем команды назначается:"
    sheet["E5"] = representative
    sheet.append([])
    sheet.append([])
    sheet.append([])
    sheet.append(["№ п/п", "Фамилия ", "Имя", "Отчество (можно оставить пустым)", "Год рождения", "Пол", "Разряд", "Сет", "Футболка (размер или оставить пустым)"])
    sheet.append([1, surname, "Петр", None, 2013, "М", "2 юношеский", 1, shirt_size])
    content = BytesIO()
    workbook.save(content)
    return content.getvalue()


def operation_headers(auth_headers: dict[str, str]) -> dict[str, str]:
    return {**auth_headers, "X-Operation-Id": str(uuid.uuid4())}


def test_public_application_can_be_downloaded_imported_and_deleted(client, festival, auth_headers):
    content = application_xlsx()
    submitted = client.post(
        "/api/v1/public/applications",
        files={"file": ("Заявка Высота.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert submitted.status_code == 201, submitted.text
    application_id = submitted.json()["id"]
    assert submitted.json()["participant_count"] == 1
    assert submitted.json()["status"] == "pending"

    repeated = client.post(
        "/api/v1/public/applications",
        files={"file": ("Заявка Высота.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == application_id

    listed = client.get("/api/v1/admin/applications", headers=auth_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [application_id]

    downloaded = client.get(f"/api/v1/admin/applications/{application_id}/download", headers=auth_headers)
    assert downloaded.status_code == 200
    assert downloaded.content == content

    imported = client.post(
        f"/api/v1/admin/applications/{application_id}/import",
        headers=operation_headers(auth_headers),
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1

    imported_again = client.post(
        f"/api/v1/admin/applications/{application_id}/import",
        headers=operation_headers(auth_headers),
    )
    assert imported_again.status_code == 409

    with SessionLocal() as db:
        participant = db.scalar(select(Participant))
        db.delete(participant)
        db.commit()
    reimported = client.post(
        f"/api/v1/admin/applications/{application_id}/import",
        headers=operation_headers(auth_headers),
    )
    assert reimported.status_code == 200, reimported.text
    assert reimported.json()["imported"] == 1
    assert reimported.json()["import_count"] == 2
    listed_again = client.get("/api/v1/admin/applications", headers=auth_headers).json()
    assert listed_again[0]["import_count"] == 2

    deleted = client.delete(
        f"/api/v1/admin/applications/{application_id}",
        headers=operation_headers(auth_headers),
    )
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 0
        participant = db.scalar(select(Participant))
        assert participant is not None
        assert participant.club == "Высота"
        assert participant.merch_size == "S"


def test_public_application_accepts_empty_shirt_size(client, festival):
    response = client.post(
        "/api/v1/public/applications",
        files={
            "file": (
                "Заявка без футболки.xlsx",
                application_xlsx("Безфутболкин", None),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["participant_count"] == 1


def test_public_application_is_duplicated_to_telegram_once(client, festival, monkeypatch):
    delivered = []

    async def capture_delivery(**application):
        delivered.append(application)

    monkeypatch.setattr("app.routers.applications.send_application_document", capture_delivery)
    content = application_xlsx("Телеграмов")

    first = client.post(
        "/api/v1/public/applications",
        files={"file": ("Заявка Телеграм.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    repeated = client.post(
        "/api/v1/public/applications",
        files={"file": ("Заявка Телеграм.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert first.status_code == 201, first.text
    assert repeated.status_code == 201, repeated.text
    assert delivered == [{
        "filename": "Заявка Телеграм.xlsx",
        "content": content,
        "participant_count": 1,
    }]


def test_same_club_applications_with_different_representatives_stay_separate(client, festival, auth_headers):
    application_ids = []
    for surname, representative in (("Первый", "Иванов Иван"), ("Второй", "Петров Пётр")):
        response = client.post(
            "/api/v1/public/applications",
            files={"file": (
                f"Заявка {representative}.xlsx",
                application_xlsx(surname=surname, team_name="Высота", representative=representative),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )},
        )
        assert response.status_code == 201, response.text
        application_ids.append(response.json()["id"])

    for application_id in application_ids:
        imported = client.post(
            f"/api/v1/admin/applications/{application_id}/import",
            headers=operation_headers(auth_headers),
        )
        assert imported.status_code == 200, imported.text

    clubs = client.get("/api/v1/admin/clubs", headers=auth_headers)
    assert clubs.status_code == 200, clubs.text
    height_clubs = [club for club in clubs.json() if club["name"] == "Высота"]
    assert [club["representative"] for club in height_clubs] == ["Иванов Иван", "Петров Пётр"]
    assert [club["participant_count"] for club in height_clubs] == [1, 1]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Club).where(Club.name == "Высота")) == 2


def test_public_application_rejects_invalid_template(client, festival):
    response = client.post(
        "/api/v1/public/applications",
        files={"file": ("Заявка.xlsx", b"not an xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationFile)) == 0


def test_file_can_be_received_after_final_start_but_not_imported(client, festival, auth_headers):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.final_started_at = datetime.now(timezone.utc)
        db.commit()
    submitted = client.post(
        "/api/v1/public/applications",
        files={"file": ("Поздняя заявка.xlsx", application_xlsx("Поздний"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert submitted.status_code == 201, submitted.text
    imported = client.post(
        f"/api/v1/admin/applications/{submitted.json()['id']}/import",
        headers=operation_headers(auth_headers),
    )
    assert imported.status_code == 409
    assert "запуска финала" in imported.json()["detail"]
