import csv
import io
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.clubs import get_or_create_club
from app.models import ApplicationType, CompetitionSet, Event, Participant, ParticipantSource, SetStatus, Sex
from app.participant_fields import normalize_merch_size
from app.services import participant_age_error


REQUIRED_COLUMNS = ("Фамилия", "Имя", "Отчество", "Дата рождения", "Пол", "Разряд", "Клуб", "Сет")
FESTIVAL_TEMPLATE_HEADERS = ("Фамилия", "Имя", "Отчество", "Год рождения", "Пол", "Разряд", "Сет")
FESTIVAL_TEMPLATE_OPTIONAL_HEADERS = ("Футболка",)
TEXT_LENGTH_LIMITS = {
    "Фамилия": 100,
    "Имя": 100,
    "Отчество": 100,
    "Разряд": 50,
    "Клуб": 200,
    "Представитель": 200,
}


@dataclass
class ImportAnalysis:
    rows: list[dict]
    parsed_rows: list[dict]
    duplicates: int
    errors: int
    overflow: list[dict]

    def response(self) -> dict:
        valid = len(self.parsed_rows) - self.duplicates
        return {
            "total_rows": len(self.rows), "valid_rows": valid,
            "duplicate_rows": self.duplicates, "error_rows": self.errors,
            "rows": self.rows, "overflow": self.overflow,
            "can_import": self.errors == 0 and valid > 0,
        }


def read_rows(filename: str, content: bytes) -> list[dict[str, object]]:
    try:
        if filename.lower().endswith(".csv"):
            decoded = content.decode("utf-8-sig")
            lines = decoded.splitlines()
            if not lines:
                return []
            return list(csv.DictReader(io.StringIO(decoded), delimiter=";" if ";" in lines[0] else ","))
        if filename.lower().endswith(".xlsx"):
            sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
            values = list(sheet.iter_rows(values_only=True))
            if not values:
                return []
            template_rows = read_festival_template(values)
            if template_rows is not None:
                return template_rows
            headers = [str(value or "").strip() for value in values[0]]
            return [dict(zip(headers, row, strict=False)) for row in values[1:] if any(value is not None for value in row)]
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Не удалось прочитать CSV. Сохраните файл в кодировке UTF-8.") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Не удалось прочитать файл: {exc}") from exc
    raise HTTPException(status_code=422, detail="Поддерживаются только файлы CSV и XLSX")


def read_festival_template(values: list[tuple[object, ...]]) -> list[dict[str, object]] | None:
    header_row = next((index for index, row in enumerate(values) if {
        festival_template_header(value) for value in row if festival_template_header(value)
    }.issuperset(FESTIVAL_TEMPLATE_HEADERS)), None)
    if header_row is None:
        return None

    team_name = template_field(values, "название команды")
    representative = template_field(values, "представителем команды назначается")
    if not team_name:
        raise HTTPException(status_code=422, detail="Заполните обязательное поле «Название команды»")
    if not representative:
        raise HTTPException(status_code=422, detail="Заполните обязательное поле «Представителем команды назначается»")

    headers = [festival_template_header(value) for value in values[header_row]]
    rows = []
    for row in values[header_row + 1:]:
        source = dict(zip(headers, row, strict=False))
        if not any(source.get(column) is not None for column in (*FESTIVAL_TEMPLATE_HEADERS, *FESTIVAL_TEMPLATE_OPTIONAL_HEADERS)):
            continue
        rows.append({
            "Фамилия": source.get("Фамилия"),
            "Имя": source.get("Имя"),
            "Отчество": source.get("Отчество"),
            "Год рождения": source.get("Год рождения"),
            "Дата рождения": source.get("Год рождения"),
            "Пол": source.get("Пол"),
            "Разряд": source.get("Разряд"),
            "Клуб": team_name,
            "Представитель": representative,
            "Сет": source.get("Сет"),
            "Футболка": source.get("Футболка"),
        })
    return rows


def festival_template_header(value: object) -> str | None:
    normalized = normalize(value)
    for header in (*FESTIVAL_TEMPLATE_HEADERS, *FESTIVAL_TEMPLATE_OPTIONAL_HEADERS):
        if normalized.startswith(normalize(header)):
            return header
    return None


def template_field(values: list[tuple[object, ...]], label: str) -> str:
    normalized_label = normalize(label)
    for row in values:
        for index, value in enumerate(row):
            if normalize(value).startswith(normalized_label):
                for candidate in row[index + 1:]:
                    if str(candidate or "").strip():
                        return str(candidate).strip()
    return ""


def normalize(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def parse_birth_date(value: object):
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    year_text = str(value).strip()
    if isinstance(value, str):
        year_text = year_text.removesuffix("г.").removesuffix("г").strip()
    if isinstance(value, int) or (year_text.isdigit() and len(year_text) == 4):
        try:
            return date(int(year_text), 1, 1)
        except ValueError as exc:
            raise ValueError("укажите год рождения четырьмя цифрами") from exc
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip(), pattern).date()
        except ValueError:
            pass
    raise ValueError("укажите дату в формате ДД.ММ.ГГГГ")


def identity(item: dict) -> tuple:
    return (
        normalize(item["surname"]), normalize(item["name"]), normalize(item["patronymic"]), item["birth_date"].year,
    )


def analyze(db: Session, event: Event, rows: list[dict[str, object]]) -> ImportAnalysis:
    if not rows:
        raise HTTPException(status_code=422, detail="Файл не содержит участников")
    if "Set" in rows[0] and "Сет" not in rows[0]:
        for row in rows:
            row["Сет"] = row.get("Set")
    missing = set(REQUIRED_COLUMNS) - set(rows[0])
    if missing:
        raise HTTPException(status_code=422, detail=f"Не хватает колонок: {', '.join(sorted(missing))}")

    competition_sets = list(db.scalars(select(CompetitionSet).where(
        CompetitionSet.event_id == event.id).order_by(CompetitionSet.name)).all())
    sets_by_name = {normalize(item.name): item for item in competition_sets}
    for item in competition_sets:
        number = "".join(char for char in item.name if char.isdigit())
        if number:
            sets_by_name[number] = item
            sets_by_name[f"сет {number}"] = item

    existing = list(db.scalars(select(Participant).where(
        Participant.event_id == event.id, Participant.archived_at.is_(None))).all())
    existing_identities = {
        (normalize(item.surname), normalize(item.name), normalize(item.patronymic), item.birth_year or item.birth_date.year)
        for item in existing
    }
    seen: set[tuple] = set()
    preview_rows: list[dict] = []
    parsed_rows: list[dict] = []
    duplicate_count = 0
    error_count = 0

    for row_number, row in enumerate(rows, start=2):
        values = {key: "" if value is None else str(value) for key, value in row.items() if key}
        merch_size = row.get("Футболка") if "Футболка" in row else row.get("Мерч")
        values["Футболка"] = "" if merch_size is None else str(merch_size)
        errors: dict[str, str] = {}
        birth_column = "Год рождения" if "Год рождения" in row else "Дата рождения"
        for column in REQUIRED_COLUMNS:
            source_column = birth_column if column == "Дата рождения" else column
            if column != "Отчество" and not str(row.get(column) or "").strip():
                errors[source_column] = "обязательное поле"
        for column, max_length in TEXT_LENGTH_LIMITS.items():
            if len(str(row.get(column) or "").strip()) > max_length:
                errors[column] = f"не более {max_length} символов"
        normalized_merch_size = None
        try:
            normalized_merch_size = normalize_merch_size(merch_size)
        except ValueError as exc:
            errors["Футболка" if "Футболка" in row else "Мерч"] = str(exc)
        birth_date = None
        if birth_column not in errors:
            try:
                birth_date = parse_birth_date(row.get("Дата рождения"))
                # В предпросмотре всегда показываем ровно год, даже если Excel
                # отдал ячейку как дату с нулевым временем.
                values[birth_column] = str(birth_date.year)
                if age_error := participant_age_error(birth_date, event.starts_on):
                    errors[birth_column] = age_error
            except ValueError as exc:
                errors[birth_column] = str(exc)
        sex = None
        sex_value = normalize(row.get("Пол"))
        if sex_value in {"м", "муж", "мужской", "male"}:
            sex = Sex.male
        elif sex_value in {"ж", "жен", "женский", "female"}:
            sex = Sex.female
        elif "Пол" not in errors:
            errors["Пол"] = "допустимо: мужской или женский"
        competition_set = sets_by_name.get(normalize(row.get("Сет")))
        if not competition_set and "Сет" not in errors:
            errors["Сет"] = "сет не найден"
        elif competition_set and competition_set.status == SetStatus.confirmed:
            errors["Сет"] = "сет уже завершён"

        duplicate = False
        parsed = None
        if not errors:
            participant = {
                "surname": str(row["Фамилия"]).strip(), "name": str(row["Имя"]).strip(),
                "patronymic": str(row.get("Отчество") or "").strip(), "birth_date": birth_date,
                "birth_year": birth_date.year,
                "sex": sex, "sport_rank": str(row["Разряд"]).strip(), "club": str(row["Клуб"]).strip(),
                "representative": str(row.get("Представитель") or "").strip(),
                "merch_size": normalized_merch_size,
            }
            item_identity = identity(participant)
            duplicate = item_identity in existing_identities or item_identity in seen
            seen.add(item_identity)
            parsed = {"row_number": row_number, "participant": participant, "competition_set": competition_set, "duplicate": duplicate}
            parsed_rows.append(parsed)
            if duplicate:
                duplicate_count += 1
        else:
            error_count += 1
        preview_rows.append({
            "row_number": row_number, "values": values, "errors": errors,
            "duplicate": duplicate, "valid": not errors and not duplicate,
        })

    current_counts = Counter(item.set_id for item in existing)
    incoming_counts = Counter(item["competition_set"].id for item in parsed_rows if not item["duplicate"])
    overflow = []
    for competition_set in competition_sets:
        incoming = incoming_counts[competition_set.id]
        projected = current_counts[competition_set.id] + incoming
        if projected > competition_set.capacity:
            overflow.append({
                "set_id": str(competition_set.id), "set_name": competition_set.name,
                "capacity": competition_set.capacity, "current": current_counts[competition_set.id],
                "incoming": incoming, "projected": projected, "overflow_by": projected - competition_set.capacity,
            })
    return ImportAnalysis(preview_rows, parsed_rows, duplicate_count, error_count, overflow)


def create_participants_from_analysis(
    db: Session,
    event: Event,
    analysis: ImportAnalysis,
    *,
    application_type: ApplicationType,
    operation_id: uuid.UUID,
) -> dict[str, int]:
    accepted = [item for item in analysis.parsed_rows if not item["duplicate"]]
    if not accepted:
        raise HTTPException(status_code=422, detail="В заявке нет корректных новых участников")
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:event_id))"), {"event_id": str(event.id)})
    next_number = (db.scalar(select(func.max(Participant.start_number)).where(
        Participant.event_id == event.id)) or 0) + 1
    for offset, parsed in enumerate(accepted):
        club = get_or_create_club(
            db, event.id, parsed["participant"]["club"], parsed["participant"]["representative"],
        )
        db.add(Participant(
            event_id=event.id, set_id=parsed["competition_set"].id,
            club_id=club.id, start_number=next_number + offset,
            application_type=application_type, source=ParticipantSource.import_file,
            import_operation_id=operation_id, **parsed["participant"],
        ))
    return {
        "imported": len(accepted), "skipped_duplicates": analysis.duplicates,
        "first_start_number": next_number, "last_start_number": next_number + len(accepted) - 1,
    }
