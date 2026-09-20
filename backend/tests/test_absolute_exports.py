from conftest import refresh_publication

import io
import uuid
from datetime import date

from openpyxl import load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Admin, AgeGroup, Ascent, Event, EventStage, FinalCategoryResult, FinalRouteAttempt, Participant, Sex, UserRole
from test_stage8_judge import prepare_final, command_headers


def configure(db, event_id):
    event = db.get(Event, event_id)
    event.export_competition_name = "ПаркРок"
    event.export_location = "Хабаровск"
    event.export_dates = "16–18 октября 2026"
    event.export_official_name = "Иванова А.А."
    event.export_official_qualification = "СС 1К"


def test_absolute_combines_sexes_and_ages_with_shared_places(client, festival):
    with SessionLocal() as db:
        db.add(AgeGroup(event_id=festival["event_id"], name="М 10–12", sex=Sex.male, min_age=10, max_age=12, sort_order=3))
        for index, (sex, year, route_ids) in enumerate([
            (Sex.male, 1990, festival["route_ids"]),
            (Sex.female, 2000, festival["route_ids"]),
            (Sex.male, 2014, festival["route_ids"][:1]),
            (Sex.female, 1998, []),
        ], 1):
            participant = Participant(event_id=festival["event_id"], club_id=festival["club_id"], set_id=festival["first_set_id"],
                start_number=index, surname=f"Участник{index}", name="Тест", birth_date=date(year, 1, 1), sex=sex, club="Клуб")
            db.add(participant); db.flush()
            for route_id in route_ids:
                db.add(Ascent(participant_id=participant.id, route_id=route_id, is_completed=True))
        db.commit()
    refresh_publication()
    response = client.get("/api/v1/public/absolute-results?stage=qualification")
    assert response.status_code == 200
    rows = response.json()["results"]
    assert [row["score"] for row in rows] == [300, 300, 100, None]
    assert [row["place"] for row in rows] == [1, 1, 3, None]
    assert {row["group_name"] for row in rows} == {"Мужчины", "Женщины", "М 10–12"}
    assert all("birth_year" not in row and "is_paid" not in row for row in rows)
    refresh_publication()
    assert client.get("/api/v1/public/absolute-results?stage=final").json()["available"] is False
    refresh_publication()
    assert client.get("/api/v1/public/absolute-results?stage=invalid").status_code == 422
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).is_public = False
        db.commit()
    refresh_publication()
    assert client.get("/api/v1/public/absolute-results").status_code == 404


def test_exports_catalog_guards_empty_data_settings_and_roles(client, festival, auth_headers):
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        event.stage = EventStage.preparation
        configure(db, event.id)
        db.commit()
    catalog = client.get("/api/v1/admin/exports/catalog", headers=auth_headers)
    assert catalog.status_code == 200, catalog.text
    assert all(not item["available"] for item in catalog.json()["items"])
    assert {item["key"] for item in catalog.json()["items"] if item["block"] == "other"} == {
        "other:participants", "other:clubs", "other:finalists", "other:finishers", "other:paid", "other:unpaid", "other:merch"}
    assert client.get("/api/v1/admin/exports/files/absolute:final.xlsx", headers=auth_headers).status_code == 409
    assert client.get("/api/v1/admin/exports/catalog").status_code == 401
    for role, code in [(UserRole.reception, 403), (UserRole.route_judge, 403), (UserRole.secretary, 200), (UserRole.chief_judge, 200)]:
        with SessionLocal() as db:
            db.get(Admin, festival["admin_id"]).role = role
            db.commit()
        assert client.get("/api/v1/admin/exports/catalog", headers=auth_headers).status_code == code


def test_final_overall_exports_and_other_datasets(client, festival, auth_headers):
    with SessionLocal() as db:
        group = db.scalar(select(AgeGroup).where(AgeGroup.name == "Мужчины"))
        group.gold_min_points = 300
        group.gold_max_points = None
        db.commit()
    participant, routes = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        configure(db, festival["event_id"])
        person = db.get(Participant, uuid.UUID(participant["id"]))
        person.is_paid = True
        person.merch_issued = True
        person.representative = "=1+1"
        result = db.scalar(select(FinalCategoryResult))
        result.score_tenths = 249
        db.add(FinalRouteAttempt(event_id=festival["event_id"], final_category_result_id=result.id,
            final_route_id=uuid.UUID(routes[0]["id"]), zone_attempt=1, top_attempt=2))
        # Configure both groups so the ordinary confirmation endpoint can approve them.
        db.commit()
    refresh_publication()
    final = client.get("/api/v1/public/absolute-results?stage=final").json()["results"]
    refresh_publication()
    overall = client.get("/api/v1/public/absolute-results?stage=overall").json()["results"]
    assert final[0]["score"] == 24.9
    assert overall[0]["score"] == 324.9
    assert overall[0]["qualification_points"] == 300
    setup = client.get("/api/v1/admin/final/setup", headers=auth_headers).json()
    for category in setup["categories"]:
        configured = client.put(f"/api/v1/admin/final/categories/{category['id']}/routes", headers=command_headers(auth_headers),
            json={"expected_event_version": setup["event_version"], "route_ids": [route["id"] for route in routes[:4]]})
        if category["route_ids"]:
            continue  # Already configured; changing routes after results is intentionally forbidden.
        assert configured.status_code == 200, configured.text
        setup = configured.json()
    status = client.get("/api/v1/admin/final", headers=auth_headers).json()
    confirmed = client.post("/api/v1/admin/final/final-results/confirm-all", headers=command_headers(auth_headers), json={"expected_version": status["event_version"]})
    assert confirmed.status_code == 200, confirmed.text
    assert client.get("/api/v1/admin/exports/files/absolute:final.xlsx", headers=auth_headers).status_code == 409
    exported = client.get("/api/v1/admin/exports/files/absolute:final.xlsx?confirm_incomplete=true", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    sheet = load_workbook(io.BytesIO(exported.content)).active
    assert sheet["C4"].value == "Абсолют · финал"
    assert sheet["J7"].value == 24.9
    assert sheet["A5"].value.startswith("Зам. Главного судьи")
    assert sheet.freeze_panes == "C7"
    assert client.get("/api/v1/admin/exports/files/absolute:overall.xlsx?confirm_incomplete=true", headers=auth_headers).status_code == 409
    for key in ("participants", "clubs", "finalists", "finishers", "paid", "merch"):
        exported = client.get(f"/api/v1/admin/exports/files/other:{key}.xlsx?confirm_incomplete=true", headers=auth_headers)
        assert exported.status_code == 200, exported.text
        sheet = load_workbook(io.BytesIO(exported.content)).active
        if key in ("participants", "finishers", "merch"):
            assert sheet["K7"].value == "=1+1" and sheet["K7"].data_type == "s"
        elif key == "finalists":
            assert [sheet.cell(6, column).value for column in range(1, 5)] == ["Возрастная группа", "ФИО", "Год рождения", "Разряд"]
            assert sheet["A7"].value == "Мужчины"
            assert sheet["B7"].value == f"{participant['surname']} {participant['name']} {participant['patronymic']}".strip()
            assert sheet["C7"].value == participant["birth_year"]
            assert sheet["D7"].value == participant["sport_rank"]
            assert sheet["E7"].value is None
        if key == "finishers":
            assert sheet["M7"].value == "Золото"
    assert client.get("/api/v1/admin/exports/files/other:unpaid.xlsx", headers=auth_headers).status_code == 409
    completed = client.post("/api/v1/admin/final/complete", headers=command_headers(auth_headers), json={"expected_version": confirmed.json()["event_version"]})
    assert completed.status_code == 200, completed.text
    exported = client.get("/api/v1/admin/exports/files/absolute:overall.xlsx?confirm_incomplete=true", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    assert load_workbook(io.BytesIO(exported.content)).active["J7"].value == 324.9


def test_overall_keeps_nonfinalists_and_qualification_snapshot(client, festival, auth_headers):
    _, _ = prepare_final(client, festival, auth_headers)
    with SessionLocal() as db:
        configure(db, festival["event_id"])
        from app.models import QualificationResultSnapshot, Route
        snapshot = db.scalar(select(QualificationResultSnapshot))
        snapshot.is_finalist = False
        # Simulate a category without a final: the qualification snapshot remains the source.
        db.query(FinalCategoryResult).delete()
        for group in db.scalars(select(AgeGroup)):
            group.finalist_count = 0
        db.get(Event, festival["event_id"]).stage = EventStage.completed
        db.get(Route, festival["route_ids"][0]).points = 9999
        db.commit()
    refresh_publication()
    overall = client.get("/api/v1/public/absolute-results?stage=overall").json()["results"]
    assert overall[0]["score"] == 300
    assert overall[0]["final_points"] is None
    response = client.get("/api/v1/admin/exports/files/absolute:overall.xlsx", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert load_workbook(io.BytesIO(response.content)).active["J7"].value == 300


def test_simplified_club_and_payment_workbooks(client, festival, auth_headers):
    clubs = ["Ястреб", "Альфа", "Клуб/А", "Клуб:А", "Очень длинное название клуба для проверки А", "Очень длинное название клуба для проверки Б", "", "Без клуба"]
    with SessionLocal() as db:
        configure(db, festival["event_id"])
        for index, club in enumerate(clubs, 1):
            for paid in (True, False):
                db.add(Participant(event_id=festival["event_id"], club_id=festival["club_id"], set_id=festival["first_set_id"],
                    start_number=index * 2 + int(paid), surname="=1+1" if index == 1 else f"Участник{index}",
                    name="Тест", birth_date=date(2000, 1, 1), sex=Sex.male, club=club, is_paid=paid))
        db.commit()
    exported = client.get("/api/v1/admin/exports/files/other:clubs.xlsx", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    workbook = load_workbook(io.BytesIO(exported.content))
    assert len(workbook.worksheets) == len(clubs)
    assert len({name.casefold() for name in workbook.sheetnames}) == len(clubs)
    assert all(len(name) <= 31 and not any(char in name for char in r"\/*?:[]") for name in workbook.sheetnames)
    exported_numbers = []
    for sheet in workbook:
        assert [sheet.cell(6, column).value for column in range(1, 4)] == ["ФИО", "Год рождения", "Стартовый номер"]
        assert sheet.auto_filter.ref == "A6:C8"
        assert sheet["D7"].value is None
        assert sheet["B7"].value == 2000
        exported_numbers.extend([sheet["C7"].value, sheet["C8"].value])
    assert sorted(exported_numbers) == list(range(2, 18))
    for key in ("paid", "unpaid"):
        exported = client.get(f"/api/v1/admin/exports/files/other:{key}.xlsx", headers=auth_headers)
        assert exported.status_code == 200, exported.text
        workbook = load_workbook(io.BytesIO(exported.content))
        assert len(workbook.worksheets) == 1
        sheet = workbook.worksheets[0]
        assert [sheet.cell(6, column).value for column in range(1, 4)] == ["ФИО", "Год рождения", "Клуб"]
        assert sheet.auto_filter.ref == "A6:C14"
        assert sheet.auto_filter.sortState.sortCondition[0].ref == "C7:C14"
        assert [sheet.cell(row, 3).value or "" for row in range(7, 15)] == sorted(clubs, key=str.casefold)
        assert sheet["D7"].value is None
        assert sheet["A14"].value == "=1+1 Тест" and sheet["A14"].data_type == "s"
