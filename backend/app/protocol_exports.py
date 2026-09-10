import io
import re
from dataclasses import dataclass

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.worksheet.page import PageMargins


@dataclass(frozen=True)
class ProtocolRow:
    place: int | None
    full_name: str
    club: str
    birth_year: int
    sport_rank: str
    completed_count: int
    points: int
    top_count: int | None = None
    zone_count: int | None = None
    top_attempts: int | None = None
    zone_attempts: int | None = None


def competition_heading(base_name: str, min_age: int) -> str:
    cleaned = re.sub(r"^(первенство|чемпионат)\s+", "", base_name.strip(), flags=re.IGNORECASE)
    kind = "Чемпионат" if min_age >= 18 else "Первенство"
    return f"{kind} {cleaned}"


def official_heading(name: str, qualification: str) -> str:
    return f"Зам. Главного судьи по виду - {name.strip()} ({qualification.strip()})"


def create_protocol_xlsx(
    *,
    competition_name: str,
    location: str,
    dates: str,
    official_name: str,
    official_qualification: str,
    category_name: str,
    category_min_age: int,
    stage: str,
    rows: list[ProtocolRow],
) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Лист1"

    sheet.column_dimensions["A"].width = 5
    sheet.column_dimensions["B"].width = 22.109375
    sheet.column_dimensions["C"].width = 22.109375
    sheet.column_dimensions["D"].width = 4.5546875
    sheet.column_dimensions["E"].width = 6.109375
    for column in "FGHIJKLM":
        sheet.column_dimensions[column].width = 3.88671875
    sheet.column_dimensions["N"].width = 5.33203125
    sheet.column_dimensions["O"].width = 12
    sheet.row_dimensions[7].height = 12.6

    for merged_range in (
        "C1:I1", "A2:D2", "E2:O2", "C3:I3", "C4:I4", "A5:C5",
        "A6:A7", "B6:B7", "C6:C7", "D6:D7", "E6:E7",
        "F6:I6", "F7:G7", "H7:I7", "J6:M6", "N6:N7", "O6:O7",
    ):
        sheet.merge_cells(merged_range)

    sheet["C1"] = competition_heading(competition_name, category_min_age)
    sheet["A2"] = location
    sheet["E2"] = dates
    sheet["C3"] = (
        "ИТОГОВЫЙ ПРОТОКОЛ КВАЛИФИКАЦИИ"
        if stage == "qualification"
        else "ИТОГОВЫЙ ПРОТОКОЛ РЕЗУЛЬТАТОВ"
    )
    sheet["C4"] = f"{category_name} - Боулдеринг"
    sheet["A5"] = official_heading(official_name, official_qualification)

    sheet["A6"] = "Место"
    sheet["B6"] = "Фамилия, имя"
    sheet["C6"] = "Команда"
    sheet["D6"] = "Г.р."
    sheet["E6"] = "Разряд"
    sheet["F6"] = "Квалификация"
    sheet["F7"] = "Трассы"
    sheet["H7"] = "Очков"
    sheet["J6"] = "Финал"
    sheet["J7"] = "Т"
    sheet["K7"] = "З"
    sheet["L7"] = "п. Т"
    sheet["M7"] = "п. З"
    sheet["N6"] = "Вып.\nразр."
    sheet["O6"] = "Баллы"

    last_row = max(23, 7 + len(rows))
    for row_number in range(8, last_row + 1):
        sheet.merge_cells(start_row=row_number, start_column=6, end_row=row_number, end_column=7)
        sheet.merge_cells(start_row=row_number, start_column=8, end_row=row_number, end_column=9)

    for row_number, item in enumerate(rows, start=8):
        values = {
            "A": item.place,
            "B": item.full_name,
            "C": item.club,
            "D": item.birth_year,
            "E": int(item.sport_rank) if item.sport_rank.isdigit() else item.sport_rank,
            "F": item.completed_count,
            "H": item.points,
            "J": item.top_count,
            "K": item.zone_count,
            "L": item.top_attempts,
            "M": item.zone_attempts,
        }
        for column, value in values.items():
            sheet[f"{column}{row_number}"] = value

    sheet["C1"].font = Font(name="Calibri", size=11, bold=True, color="FF000000")
    sheet["C3"].font = Font(name="Calibri", size=11, bold=True, color="FF000000")
    sheet["C4"].font = Font(name="Calibri", size=11, bold=True, color="FF000000")
    sheet["A5"].font = Font(name="Calibri", size=10, color="FF000000")
    for cell in ("C1", "C3", "C4"):
        sheet[cell].alignment = Alignment(horizontal="center", vertical="center")
    sheet["A2"].alignment = Alignment(horizontal="left", vertical="center")
    sheet["E2"].alignment = Alignment(horizontal="right", vertical="center")
    sheet["A5"].alignment = Alignment(horizontal="left", vertical="center")

    thin = Side(style="thin", color="FF000000")
    thick = Side(style="thick", color="FF000000")
    for row_number in range(6, last_row + 1):
        for column_number in range(1, 16):
            cell = sheet.cell(row=row_number, column=column_number)
            cell.font = Font(name="Calibri", size=9, color="FF000000")
            cell.alignment = Alignment(
                horizontal="left" if column_number in (2, 3) and row_number >= 8 else "center",
                vertical="center",
                wrap_text=column_number in (4, 14),
            )
            left = thick if column_number in (6, 10, 14) else thin
            right = thick if column_number in (5, 9, 13) else thin
            cell.border = Border(left=left, right=right, top=thin, bottom=thin)

    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins = PageMargins(left=0.7, right=0.7, top=0.75, bottom=0.75, header=0.3, footer=0.3)
    sheet.print_area = f"A1:O{last_row}"
    sheet.sheet_view.selection[0].activeCell = "A1"
    sheet.sheet_view.selection[0].sqref = "A1"

    output = io.BytesIO()
    for row in sheet:
        for cell in row:
            if cell.data_type == "f":
                cell.data_type = "s"
    workbook.save(output)
    return output.getvalue()


def create_table_xlsx(*, title: str, headers: list[str], rows: list[list], **settings) -> bytes:
    """Keep the shared protocol heading, typography and print setup for data tables."""
    workbook = load_workbook(io.BytesIO(create_protocol_xlsx(
        **settings, category_name=title, category_min_age=0, stage="qualification", rows=[],
    )))
    sheet = workbook.active
    sheet["C1"] = settings["competition_name"]
    sheet["C3"] = "ВЫГРУЗКА РЕЗУЛЬТАТОВ И ДАННЫХ"
    sheet["C4"] = title
    for merged in list(sheet.merged_cells.ranges):
        if merged.min_row >= 6:
            sheet.unmerge_cells(str(merged))
    sheet.delete_rows(6, sheet.max_row)
    thin = Side(style="thin", color="FF000000")
    for row_number, values in enumerate([headers, *rows], 6):
        for column_number, value in enumerate(values, 1):
            cell = sheet.cell(row_number, column_number, value)
            if isinstance(value, str):
                cell.data_type = "s"
            cell.font = Font(name="Calibri", size=9, bold=row_number == 6, color="FF000000")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            if isinstance(value, float):
                cell.number_format = "0.0"
        sheet.row_dimensions[row_number].height = 32 if row_number == 6 else 30
    for index, header in enumerate(headers, 1):
        sheet.column_dimensions[get_column_letter(index)].width = 25 if header in ("ФИО", "Клуб", "Представитель") else 14
    sheet.auto_filter.ref = f"A6:{get_column_letter(len(headers))}{max(6, 6 + len(rows))}"
    sheet.freeze_panes = "C7"
    sheet.print_title_rows = "1:6"
    sheet.print_area = f"A1:O{max(7, 6 + len(rows))}"
    sheet.page_setup.orientation = "landscape"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
