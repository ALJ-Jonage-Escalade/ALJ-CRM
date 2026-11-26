"""
Export Excel du planning hebdomadaire des créneaux (bouton de l'onglet Créneaux).

Construit une grille « Lundi → Samedi », de 9h à 22h par pas de 30 minutes :
- un bloc fusionné par créneau, coloré selon le type de groupe
  (compétition = vert, perfectionnement = rose, cours = bleu, autonome = gris) ;
- le libellé du groupe (suffixe parenthésé « (jour / horaire) » retiré) ;
- une ligne encadrants : noms complets si la place le permet, sinon **initiales**
  (bloc trop court), sinon rien ;
- les heures en libellés à gauche ET à droite de la grille (9h, 10h, … 22h) ;
- hiérarchie des traits : lignes d'**heures** et cadre plus marqués (medium sombre)
  que les lignes des **demi-heures** (thin clair) ; blocs au contour médium.

Logique pure et testable : parse_time_range / clean_group_label / _initials /
coaches_text / assign_lanes, puis export_planning_excel (openpyxl).
"""
from __future__ import annotations

import io
import math
import re
from typing import Any, Mapping, NamedTuple, Optional, Sequence, TypedDict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from domain.utils import normalize_string
from exports.spreadsheet_safety import neutralize_formulas

DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
GRID_START = 9 * 60    # 9h00
GRID_END = 22 * 60     # 22h00
STEP = 30              # pas de 30 minutes
CHARS_PER_LINE = 16    # largeur estimée d'une sous-colonne en caractères

# Couleurs de fond par type de groupe (inspirées du site du club)
TYPE_FILLS = {
    "compétition": "D9EAD3",       # vert clair
    "perfectionnement": "F8C8DC",  # rose
    "cours": "D9E1F2",             # bleu lavande
    "autonome": "D9D9D9",          # gris
}
DEFAULT_FILL = "EFEFEF"
FILL_BLOC_AUTONOME = "FFD8A8"      # orange clair pastel (groupe « Autonome Bloc »)
FIRST_GRID_ROW = 3                 # row 1: title, row 2: day headers

PlanningSlot = Mapping[str, Any]  # Any: a planning row (jour, groupe, type, horaires, encadrants…)

# Line weights: day separators thick black, hours and frame medium dark, half hours thin light, lanes thin
_THIN = Side(style="thin", color="BFBFBF")
_MEDIUM = Side(style="medium", color="404040")
_LANE = Side(style="thin", color="595959")
_THICK = Side(style="thick", color="000000")
_HEADER_FILL = "D9E1F2"
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


class GridSlot(TypedDict):
    """A slot placed on the grid: its minutes (clipped to the grid), label, fill colour and coaches."""
    start: int
    end: int
    label: str
    fill: str
    encadrants: list[str]


class DayColumns(NamedTuple):
    """A day's slots with their lane, and its first and last grid column."""
    assignments: list[tuple[GridSlot, int]]
    first_column: int
    last_column: int


def fill_for_item(item: PlanningSlot) -> str:
    """Couleur de fond d'un créneau : priorité au nom du groupe (« Autonome Bloc »
    = orange clair pastel), sinon le type de groupe."""
    label = normalize_string(item.get("groupe") or "")
    if "autonome" in label and "bloc" in label:
        return FILL_BLOC_AUTONOME
    return TYPE_FILLS.get(normalize_type(item.get("type")), DEFAULT_FILL)


def parse_time_range(horaires: Any) -> Optional[tuple[int, int]]:  # Any: the stored text, possibly None
    """'18:00 - 20:00', '17:00 18:00', '9h30-12h' -> (début, fin) en minutes, ou None."""
    matches = re.findall(r"(\d{1,2})\s*[:hH]\s*(\d{1,2})?", str(horaires or ""))
    values = []
    for hours_text, minutes_text in matches:
        hours, minutes = int(hours_text), int(minutes_text or 0)
        if hours > 23 or minutes > 59:
            continue
        values.append(hours * 60 + minutes)
    if len(values) < 2:
        return None
    start, end = values[0], values[1]
    if end <= start:
        return None
    return start, end


def clean_group_label(groupe: Any) -> str:  # Any: the stored group name, possibly None
    """Retire le suffixe parenthésé redondant « (jour / horaire) » de fin de libellé.

    « Enfants 2019-2020 (Mercredi 09h30) » -> « Enfants 2019-2020 » ;
    « Perfectionnement - U11-U13(1) » est conservé (le (1) distingue deux groupes).
    """
    name = str(groupe or "").strip()
    suffix = re.search(r"\(([^)]*)\)\s*$", name)
    if suffix and re.search(r"(?i)(lundi|mardi|mercredi|jeudi|vendredi|samedi|\d{1,2}\s*[h:])", suffix.group(1)):
        name = name[: suffix.start()].strip()
    return name


def _initials(name: str) -> str:
    """Initiales compactes d'un encadrant : « Camille DIDIER » -> « C.D. »."""
    words = [w for w in re.split(r"[\s\-'.]+", str(name).strip()) if w]
    return ".".join(w[0].upper() for w in words) + "." if words else ""


def coaches_text(coaches: Optional[Sequence[Any]], rows_span: int, label: str) -> str:  # Any: stored names
    """Ligne encadrants adaptée à la place du bloc (noms complets, initiales, ou rien)."""
    names = [str(coach).strip() for coach in (coaches or []) if str(coach).strip()]
    if not names or rows_span <= 0:
        return ""
    full = ", ".join(names)
    initials = ", ".join(_initials(name) for name in names)
    label_lines = max(1, math.ceil(len(label) / CHARS_PER_LINE))
    free = max(0, rows_span - label_lines)
    if math.ceil((len(full) + 7) / CHARS_PER_LINE) <= free:
        return "Enc. : " + full
    if math.ceil(len(initials) / CHARS_PER_LINE) <= free:
        return initials
    return ""


def assign_lanes(slots: Sequence[GridSlot]) -> tuple[list[tuple[GridSlot, int]], int]:
    """Répartit les créneaux d'un jour en colonnes sans chevauchement.

    slots : [{start, end, …}] (minutes). Retourne ([(slot, lane)…], nb_lanes).
    """
    lane_ends: list[int] = []
    placed: list[tuple[GridSlot, int]] = []
    for slot in sorted(slots, key=lambda x: (x["start"], x["end"])):
        for lane, lane_end in enumerate(lane_ends):
            if slot["start"] >= lane_end:
                lane_ends[lane] = slot["end"]
                placed.append((slot, lane))
                break
        else:
            lane_ends.append(slot["end"])
            placed.append((slot, len(lane_ends) - 1))
    return placed, len(lane_ends)


def normalize_type(type_value: Any) -> str:  # Any: the stored type, possibly None
    """The group type when it has a colour, else « cours »."""
    group_type = str(type_value or "").strip().lower()
    return group_type if group_type in TYPE_FILLS else "cours"


def _slots_by_day(planning_data: Optional[Sequence[PlanningSlot]]) -> dict[str, list[GridSlot]]:
    """The slots that fit on the grid (known day, readable times), by day; ValueError when there is none."""
    by_day: dict[str, list[GridSlot]] = {day: [] for day in DAYS}
    for item in planning_data or []:
        span = parse_time_range(item.get("horaires"))
        day = str(item.get("jour") or "").strip().capitalize()
        if not span or day not in DAYS:
            continue
        start = max(span[0], GRID_START)
        end = min(span[1], GRID_END)
        if end <= start:
            continue
        by_day[day].append(GridSlot(
            start=start, end=end,
            label=clean_group_label(item.get("groupe")) or str(item.get("groupe") or "Créneau"),
            fill=fill_for_item(item),
            encadrants=item.get("encadrants") or [],
        ))
    if not any(by_day.values()):
        raise ValueError("Aucun créneau exploitable dans le planning (jour + horaires requis).")
    return by_day


def _day_columns(by_day: dict[str, list[GridSlot]]) -> dict[str, DayColumns]:
    """Each day's lanes (overlapping slots side by side) and columns; column 1 holds the hours."""
    columns: dict[str, DayColumns] = {}
    offset = 0
    for day in DAYS:
        assignments, lane_count = assign_lanes(by_day[day])
        first_column = 2 + offset
        columns[day] = DayColumns(assignments, first_column, first_column + max(1, lane_count) - 1)
        offset += max(1, lane_count)
    return columns


def _write_headers(sheet: Worksheet, saison: str, days: dict[str, DayColumns], lane_total: int) -> None:
    """Row 1: the season over every lane; row 2: each day's name over its lanes."""
    sheet.merge_cells(start_row=1, start_column=2, end_row=1, end_column=1 + lane_total)
    title = sheet.cell(row=1, column=2, value=f"Saison {str(saison).replace('-', ' - ')}")
    title.font = Font(name="Calibri", size=12, bold=True)
    title.alignment = _CENTER
    for column in range(2, 2 + lane_total):
        sheet.cell(row=1, column=column).border = Border(left=_MEDIUM, right=_MEDIUM, top=_MEDIUM, bottom=_MEDIUM)

    header_fill = PatternFill("solid", fgColor=_HEADER_FILL)
    for day in DAYS:
        first, last = days[day].first_column, days[day].last_column
        if last > first:
            sheet.merge_cells(start_row=2, start_column=first, end_row=2, end_column=last)
        header = sheet.cell(row=2, column=first, value=day.upper())
        header.font = Font(name="Calibri", size=10, bold=True)
        header.alignment = _CENTER
        header.fill = header_fill
        for column in range(first, last + 1):
            cell = sheet.cell(row=2, column=column)
            cell.border = Border(left=_THICK if column == first else _LANE,
                                 right=_THICK if column == last else _LANE,
                                 top=_MEDIUM, bottom=_MEDIUM)
            cell.fill = header_fill


def _write_grid(sheet: Worksheet, days: dict[str, DayColumns], lane_total: int) -> None:
    """The half-hour rows: hour labels on both sides, hour lines medium, half-hour lines thin, day separators thick."""
    step_count = (GRID_END - GRID_START) // STEP
    day_starts = {columns.first_column for columns in days.values()}
    day_ends = {columns.last_column for columns in days.values()}
    for step in range(step_count):
        row = FIRST_GRID_ROW + step
        minutes = GRID_START + step * STEP
        sheet.row_dimensions[row].height = 15
        label = f"{minutes // 60}h" if step % 2 == 0 else ""
        for column in (1, 2 + lane_total):
            cell = sheet.cell(row=row, column=column, value=label)
            cell.font = Font(name="Calibri", size=9, bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="top")
        # Medium top on an hour (and the first row), medium bottom when the row ends on an hour (or is the last)
        top = _MEDIUM if step % 2 == 0 else _THIN
        bottom = _MEDIUM if (step % 2 == 1 or step == step_count - 1) else _THIN
        for column in range(2, 2 + lane_total):
            sheet.cell(row=row, column=column).border = Border(left=_THICK if column in day_starts else _LANE,
                                                               right=_THICK if column in day_ends else _LANE,
                                                               top=top, bottom=bottom)


def _paint_slots(sheet: Worksheet, days: dict[str, DayColumns]) -> None:
    """One merged, coloured block per slot in its lane: the group label and, when it fits, its coaches."""
    for day in DAYS:
        columns = days[day]
        for slot, lane in columns.assignments:
            start_row = FIRST_GRID_ROW + (slot["start"] - GRID_START) // STEP
            end_row = FIRST_GRID_ROW + (slot["end"] - GRID_START + STEP - 1) // STEP - 1
            coaches = coaches_text(slot["encadrants"], end_row - start_row + 1, slot["label"])
            column = columns.first_column + lane
            left = _THICK if column == columns.first_column else _MEDIUM
            right = _THICK if column == columns.last_column else _MEDIUM
            for row in range(start_row, end_row + 1):
                cell = sheet.cell(row=row, column=column)
                cell.border = Border(left=left, right=right, top=_MEDIUM, bottom=_MEDIUM)
                cell.fill = PatternFill("solid", fgColor=slot["fill"])
            sheet.merge_cells(start_row=start_row, start_column=column, end_row=end_row, end_column=column)
            block = sheet.cell(row=start_row, column=column, value=slot["label"] + (("\n" + coaches) if coaches else ""))
            block.font = Font(name="Calibri", size=8, bold=True, color="1F4E79")
            block.alignment = _CENTER


def export_planning_excel(planning_data: Optional[Sequence[PlanningSlot]], saison: str) -> bytes:
    """Classeur Excel (en mémoire) du planning hebdomadaire ; ValueError sans aucun créneau plaçable sur la grille."""
    days = _day_columns(_slots_by_day(planning_data))
    lane_total = days[DAYS[-1]].last_column - 1

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Planning"
    _write_headers(sheet, saison, days, lane_total)
    _write_grid(sheet, days, lane_total)
    _paint_slots(sheet, days)

    # Hour columns narrow on both sides, lanes wide
    sheet.column_dimensions["A"].width = 4.5
    for column in range(2, 2 + lane_total):
        sheet.column_dimensions[get_column_letter(column)].width = 13.5
    sheet.column_dimensions[get_column_letter(2 + lane_total)].width = 4.5

    # Landscape, one page wide
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True

    neutralize_formulas(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def export_planning_list_excel(planning_data: Optional[Sequence[PlanningSlot]], saison: str) -> bytes:
    """Extraction « liste » du planning : une ligne par créneau, au format de la BDD.

    Colonnes proches de la table `planning` : Jour, Groupe, Type, Horaires, Encadrants,
    Tarifs HelloAsso, Catégorie d'âge, bornes de naissance. Tri Lundi → Samedi puis
    heure de début ; les créneaux non exploitables horairement sont conservés (BDD).
    """
    headers = ["Jour", "Groupe", "Type", "Horaires", "Encadrants",
               "Tarifs HelloAsso", "Catégorie d'âge", "Naissance min", "Naissance max"]
    day_index = {day: i for i, day in enumerate(DAYS)}

    rows: list[dict[str, Any]] = []  # Any: the cell values and the sort key
    for item in planning_data or []:
        jour = str(item.get("jour") or "").strip()
        span = parse_time_range(item.get("horaires"))
        rows.append({
            "sort": (day_index.get(jour.capitalize(), len(DAYS)),
                     span[0] if span else 9999,
                     str(item.get("groupe") or "")),
            "jour": jour,
            "groupe": str(item.get("groupe") or ""),
            "type": str(item.get("type") or ""),
            "horaires": str(item.get("horaires") or ""),
            "encadrants": ", ".join(str(e).strip() for e in (item.get("encadrants") or []) if str(e).strip()),
            "tarifs": ", ".join(str(t).strip() for t in (item.get("helloasso_tarifs") or []) if str(t).strip()),
            "categorie_age": str(item.get("categorie_age") or ""),
            "naissance_min": str(item.get("naissance_min") or ""),
            "naissance_max": str(item.get("naissance_max") or ""),
        })
    rows.sort(key=lambda r: r["sort"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Planning (liste)"
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="D9E1F2")

    ws.append(headers)
    for c, _h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(name="Calibri", size=10, bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")
    display = []
    for r_data in rows:
        line = [r_data["jour"], r_data["groupe"], r_data["type"], r_data["horaires"],
                r_data["encadrants"], r_data["tarifs"], r_data["categorie_age"],
                r_data["naissance_min"], r_data["naissance_max"]]
        display.append(line)
        ws.append(line)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=ws.max_row, column=c)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    # Largeurs adaptées au contenu (bornées pour rester lisible)
    for c, h in enumerate(headers, start=1):
        longest = max([len(h)] + [len(str(line[c - 1])) for line in display]) if display else len(h)
        ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = min(42, max(10, longest + 2))
    ws.freeze_panes = "A2"

    neutralize_formulas(wb)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
