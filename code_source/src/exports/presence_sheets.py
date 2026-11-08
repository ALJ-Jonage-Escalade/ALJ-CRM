"""Attendance sheets (Excel) built from the club template, one table per planning group, in memory.

Two variants, chosen by the presence screen:
- "autonome": every autonomous group in one table, with the badge, bloc and orange passport columns, an
  « Autorisation » column, and the authorised minors of other groups added (domain/members/presence_rules.py);
- "cours": one table per course, without the badge columns; either one file per course or every table
  stacked in a single sheet (`same_sheet`), each starting on a new printed page.
"""
from __future__ import annotations

import datetime
import io
import logging
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal, NamedTuple

import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.pagebreak import Break
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

from domain.members.presence_rules import MemberRow, authorized_minors, member_identity_key, members_with_tarifs
from exports.spreadsheet_safety import neutralize_formulas, template_formulas
from infrastructure.qrcodes import find_group_qrcode, get_group_qrcode
from paths import template_path

logger = logging.getLogger("alj")

PresenceVariant = Literal["autonome", "cours"]

# A planning slot as PlanningRepository.load_planning_data returns it (groupe, jour, horaires, encadrants, helloasso_tarifs…).
PlanningItem = Mapping[str, Any]

TEMPLATE_NAME = "Template Export liste adhérents à imprimer.xlsx"
STACKED_FILENAME = "Feuilles_Presence_Toutes_Activites.xlsx"

# Compact pictogram replacing the word "Autonomes" in the « Autorisation » column
PICTO_AUTONOME = "🧗"

# Virtual export groups: several HelloAsso tariffs printed as ONE attendance table. When one is selected,
# the member tariffs it covers get no table of their own (their members would be printed twice).
VIRTUAL_GROUP_TARIFS = {
    "Adultes & Jeunes Adultes autonomes": (
        "Adultes autonomes",
        "Jeunes Adultes autonomes - nés entre 2001 et 2008",
    ),
    "Loisir - Adultes débutants": (
        "Cours Adultes débutants",
        "Cours jeunes Adultes débutants nés entre 2001 et 2008",
    ),
}

# Tariff used to find the planning slot (hours, coaches) of each virtual group, through its helloasso_tarifs.
VIRTUAL_GROUP_LOOKUP = {
    "Adultes & Jeunes Adultes autonomes": "Adultes autonomes",
    "Loisir - Adultes débutants": "Cours Adultes débutants",
}

DAY_NAME_TO_WEEKDAY = {
    "lundi": 1,
    "mardi": 2,
    "mercredi": 3,
    "jeudi": 4,
    "vendredi": 5,
    "samedi": 6,
    "dimanche": 7,
}
# Days of a group whose planning gives none (e.g. autonomous slots): Monday to Saturday
DEFAULT_GROUP_DAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi")

# Schedules printed instead of the planning slots, for groups whose slots are too many to list
AUTONOMOUS_SCHEDULE = "Lundi-Mercredi-Jeudi-Vendredi-Samedi (Créneaux autonomes)"
COMPETITION_U11_SCHEDULE = "Lun 18h-20h, Mer 16h-18h, Ven 18h-20h"
COMPETITION_SCHEDULE = "Lun 18h00-20h30, Mer 18h00-20h00, Ven 18h30-20h30"

# ============================================================================
# Official calendar of the 2026-2027 season (school holidays zone A): start/end of the courses,
# school holidays, public holidays and exceptional closures of the gym. The sheets only list real
# sessions: dates falling in these periods are left out.
# ============================================================================
SEASON_COURSE_START = datetime.date(2026, 9, 14)
SEASON_COURSE_END = datetime.date(2027, 6, 25)

PUBLIC_HOLIDAYS = {
    datetime.date(2026, 11, 11): "Armistice 1918",
    datetime.date(2027, 3, 29): "Lundi de Pâques",
    datetime.date(2027, 5, 6): "Jeudi de l'Ascension",
    datetime.date(2027, 5, 17): "Lundi de Pentecôte",
}

SCHOOL_HOLIDAYS_ZONE_A = [
    ("Toussaint", datetime.date(2026, 10, 17), datetime.date(2026, 11, 2)),
    ("Noël", datetime.date(2026, 12, 19), datetime.date(2027, 1, 4)),
    ("Hiver", datetime.date(2027, 2, 13), datetime.date(2027, 3, 1)),
    ("Printemps", datetime.date(2027, 4, 10), datetime.date(2027, 4, 26)),
]

SALLE_CLOSURES = [
    ("Championnat régional U11-U13", datetime.date(2027, 3, 19), datetime.date(2027, 4, 4)),
]

# Sheet layout: 5 header lines (group, schedule, coaches, total, spacer), then the column headers
HEADER_LINES = 5
LAST_CLEARED_COLUMN = 100   # template columns reset before writing (the template is narrower)
LAST_CLEARED_ROW = 200      # template rows reset below the member rows
QR_SIZE_PX = 90
QR_ROWS = 7                 # rows taken by the QR code image below a table
STACKED_GAP_ROWS = 2        # blank rows between two stacked tables
A3_PAPER = 8                # PAPERSIZE_A3 in Excel's page setup
MIN_READABLE_SCALE = 55     # % below which a wide table spills onto more pages instead of shrinking

# Club style: Segoe UI, dark blue 1E3A8A, zebra rows
THIN_GRAY = Side(style="thin", color="CCCCCC")
THICK_BLUE = Side(style="medium", color="1E3A8A")
MEDIUM_BLACK = Side(style="medium", color="000000")
DOUBLE_BLUE = Side(style="double", color="1E3A8A")
BORDER_CELL = Border(left=THIN_GRAY, right=THIN_GRAY, top=THIN_GRAY, bottom=THIN_GRAY)
BORDER_HEADER = Border(left=THIN_GRAY, right=THIN_GRAY, top=THICK_BLUE, bottom=DOUBLE_BLUE)
NO_BORDER = Border()
FILL_ZEBRA = PatternFill(start_color="EAEAEA", end_color="EAEAEA", fill_type="solid")
FILL_WHITE = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
FILL_HEADER = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")
NO_FILL = PatternFill(fill_type=None)
FONT_TITLE = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
FONT_INFO = Font(name="Segoe UI", size=10, bold=True, color="374151")
FONT_TOTAL = Font(name="Segoe UI", size=10, bold=True, color="1E3A8A")
FONT_HEADER = Font(name="Segoe UI", size=8, bold=True, color="374151")
FONT_MEMBER = Font(name="Segoe UI", size=9, bold=False, color="1F2937")
FONT_HEALTH_PENDING = Font(name="Segoe UI", size=10, bold=True, color="DC2626")
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")


class PresenceFile(NamedTuple):
    filename: str
    content: bytes


@dataclass(frozen=True)
class SheetGroup:
    """One attendance table: its title, the members listed and the names used to find its planning slot."""
    name: str
    members: list[MemberRow]
    lookup_name: str
    qrcode_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotInfo:
    """What the planning says about a group: the slots found, their schedule, coaches and days."""
    planning_group: str | None
    schedule: str
    coaches: list[str]
    days: list[str]
    items: list[PlanningItem] = field(default_factory=list)


@dataclass(frozen=True)
class SheetLayout:
    """Columns of a table: first name, last name, then the optional ones, then one column per session."""
    show_badges: bool
    show_authorization: bool
    show_health: bool

    @classmethod
    def for_variant(cls, variant: PresenceVariant, show_health: bool) -> SheetLayout:
        autonomous = variant == "autonome"
        return cls(show_badges=autonomous, show_authorization=autonomous, show_health=show_health)

    @property
    def authorization_column(self) -> int | None:
        return (6 if self.show_badges else 3) if self.show_authorization else None

    @property
    def health_column(self) -> int | None:
        if not self.show_health:
            return None
        return 3 + 3 * self.show_badges + self.show_authorization

    @property
    def first_date_column(self) -> int:
        return 3 + 3 * self.show_badges + self.show_authorization + self.show_health


@dataclass(frozen=True)
class TableExtent:
    """Rows and columns a written table takes, for borders, print areas and the next stacked table."""
    header_row: int
    last_member_row: int
    last_column: int
    print_bottom_row: int
    next_table_offset: int


def is_course_day(day: datetime.date) -> bool:
    """True when a session can take place that day (within the season, outside holidays and gym closures)."""
    if day < SEASON_COURSE_START or day > SEASON_COURSE_END:
        return False
    if day in PUBLIC_HOLIDAYS:
        return False
    for _, h_start, h_end in SCHOOL_HOLIDAYS_ZONE_A:
        if h_start <= day <= h_end:
            return False
    return all(not (c_start <= day <= c_end) for _, c_start, c_end in SALLE_CLOSURES)


def clean_filename(name: str) -> str:
    """A group name made safe for a file name."""
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_"))
    safe = safe.replace(" ", "_")
    safe = re.sub(r"_{2,}", "_", safe)
    return safe.strip("_")


def session_dates(group_days: Iterable[str], first_day: datetime.date | None, last_day: datetime.date | None) -> list[datetime.date]:
    """Course days of the period falling on the group's weekdays; none when the period is incomplete."""
    weekdays = {DAY_NAME_TO_WEEKDAY[d.lower()] for d in group_days if d.lower() in DAY_NAME_TO_WEEKDAY}
    if not (first_day and last_day and weekdays):
        return []
    days = []
    current = first_day
    while current <= last_day:
        if current.isoweekday() in weekdays and is_course_day(current):
            days.append(current)
        current += datetime.timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# Who goes on which table
# ---------------------------------------------------------------------------

def group_members(group_name: str, members: Sequence[MemberRow], group_tarifs: Mapping[str, Sequence[str]]) -> list[MemberRow]:
    """Members of a group: the tariffs mapped to its planning slot, else those of a virtual group, else the
    tariff named like the group."""
    tarifs = group_tarifs.get(group_name) or VIRTUAL_GROUP_TARIFS.get(group_name) or (group_name,)
    return members_with_tarifs(members, tarifs)


def _merged_lookup_name(group_names: Sequence[str]) -> str:
    """Name used to find the planning slot of merged groups: a virtual group's tariff, an autonomous group, else the first."""
    for name in group_names:
        if name in VIRTUAL_GROUP_LOOKUP:
            return VIRTUAL_GROUP_LOOKUP[name]
        if "autonome" in name.lower():
            return name
    return group_names[0]


def sheet_groups(
    selected_groups: Sequence[str],
    members: Sequence[MemberRow],
    variant: PresenceVariant,
    group_tarifs: Mapping[str, Sequence[str]],
    today: datetime.date,
) -> list[SheetGroup]:
    """The tables to print, members sorted by first name. "autonome" merges every group into one table and
    adds the authorised minors of the other groups."""
    covered_tarifs = {tarif for name in selected_groups for tarif in VIRTUAL_GROUP_TARIFS.get(name, ())}
    names = [name for name in selected_groups if name not in covered_tarifs]
    if not names:
        return []
    if variant == "autonome":
        merged_name = " & ".join(names)
        if len(merged_name) > 80:
            merged_name = "Groupes Fusionnés"
        own = [member for name in names for member in group_members(name, members, group_tarifs)]
        listed = own + authorized_minors(members, today)
        groups = [SheetGroup(
            name=merged_name if len(names) > 1 else names[0],
            members=_unique_by_identity(listed),
            lookup_name=_merged_lookup_name(names),
            qrcode_names=tuple(selected_groups),
        )]
    else:
        groups = [SheetGroup(name, group_members(name, members, group_tarifs), VIRTUAL_GROUP_LOOKUP.get(name, name)) for name in names]
    for group in groups:
        group.members.sort(key=lambda member: str(member.get("first_name") or "").strip().lower())
    return groups


def _unique_by_identity(members: Iterable[MemberRow]) -> list[MemberRow]:
    seen = set()
    unique = []
    for member in members:
        key = member_identity_key(member)
        if key not in seen:
            seen.add(key)
            unique.append(member)
    return unique


# ---------------------------------------------------------------------------
# Planning slot of a group
# ---------------------------------------------------------------------------

def _split_days(day_field: str) -> list[str]:
    """Weekday names of a planning "jour" field ("Lundi / Jeudi", "Mardi et Vendredi"…), capitalised."""
    parts = re.split(r"[/,;\s]+and\s+|[/,;\s]+et\s+|[/,;]+", day_field)
    return [part.strip().capitalize() for part in parts if part.strip().lower() in DAY_NAME_TO_WEEKDAY]


def _start_hour(hours: str) -> int | None:
    """Start hour of a planning "horaires" field ("18:00 - 20:00", "9h30-10h30"), None when unreadable."""
    found = re.match(r"\s*(\d{1,2})\s*[h:]", hours)
    return int(found.group(1)) if found else None


def _schedule_label(group_name: str, slots: Sequence[str]) -> str:
    lowered = group_name.lower()
    if "autonome" in lowered:
        return AUTONOMOUS_SCHEDULE
    if "compétition" in lowered or "competition" in lowered:
        return COMPETITION_U11_SCHEDULE if "u11" in lowered else COMPETITION_SCHEDULE
    return ", ".join(slots) or "-"


def summarize_planning_matches(matches: Sequence[PlanningItem], group_name: str) -> SlotInfo:
    """Coaches (case-insensitive, once each), slots, and weekdays of the planning items found for a group (at least one)."""
    coaches: list[str] = []
    slots: list[str] = []
    days: list[str] = []
    for item in matches:
        for coach in item.get("encadrants") or []:
            if str(coach).strip().lower() not in {c.strip().lower() for c in coaches}:
                coaches.append(str(coach))
        day_field = str(item.get("jour") or "").strip()
        hours = str(item.get("horaires") or "").strip()
        if day_field and hours and f"{day_field} {hours}" not in slots:
            slots.append(f"{day_field} {hours}")
        days.extend(day for day in _split_days(day_field) if day not in days)
    return SlotInfo(
        planning_group=str(matches[0].get("groupe") or group_name),
        schedule=_schedule_label(group_name, slots),
        coaches=coaches,
        days=days,
        items=list(matches),
    )


def planning_items_for(lookup_name: str, planning: Iterable[PlanningItem]) -> list[PlanningItem]:
    """Planning items named like the group or linked to it as a HelloAsso tariff (configured on the planning page)."""
    key = lookup_name.strip().lower()
    return [
        item for item in planning
        if str(item.get("groupe") or "").strip().lower() == key
        or any(str(tarif).strip().lower() == key for tarif in item.get("helloasso_tarifs") or [])
    ]


def planning_items_by_keywords(group_name: str, planning: Iterable[PlanningItem]) -> list[PlanningItem]:
    """Fallback for a group the planning does not name: match its keywords (level, day, hour) to the slots."""
    name = group_name.lower()
    is_autonome = "autonome" in name
    is_compet = "compétition" in name or "competition" in name
    is_youngest_compet = any(marker in name for marker in ("u11", "u13", "2015", "2016", "2017", "2018"))
    is_debutant = "débutant" in name or "debutant" in name
    is_lycee = "lycée" in name or "lycee" in name
    is_college = "collège" in name or "college" in name
    is_bloc = "bloc" in name
    is_perf = "perf" in name
    target_day = next((day for day in DAY_NAME_TO_WEEKDAY if day in name), None)
    hour_found = re.search(r"(\d{1,2})h", name)
    target_hour = int(hour_found.group(1)) if hour_found else None

    matches = []
    for item in planning:
        g_name = str(item.get("groupe") or "").lower()
        g_type = str(item.get("type") or "").lower()
        same_day = target_day is None or target_day == str(item.get("jour") or "").lower()
        if is_autonome and ("autonome" in g_name or "autonome" in g_type):
            matches.append(item)
        elif is_compet and "compétition" in g_name:
            if ("u11-u15" in g_name) if is_youngest_compet else ("u15" in g_name):
                matches.append(item)
        elif (is_bloc and "bloc" in g_name) or (is_perf and ("perf" in g_name or "difficult" in g_name)) \
                or (is_lycee and "lycée" in g_name) or (is_debutant and "débutants" in g_name):
            matches.append(item)
        elif is_college and "collège" in g_name:
            if same_day:
                matches.append(item)
        elif "enfants" in name and "enfants" in g_name:
            same_hour = target_day is None or target_hour is None or _start_hour(str(item.get("horaires") or "")) == target_hour
            if same_day and same_hour:
                matches.append(item)
    return matches


def resolve_slot(group: SheetGroup, planning: Sequence[PlanningItem]) -> SlotInfo:
    """Planning slot of a group (by name or tariff, else by keywords). Its days fall back to the weekdays in the
    group name, then to Monday-Saturday."""
    fallback_days = [day.capitalize() for day in DAY_NAME_TO_WEEKDAY if day in group.name.lower()] or list(DEFAULT_GROUP_DAYS)
    matches = planning_items_for(group.lookup_name, planning) or planning_items_by_keywords(group.name, planning)
    if not matches:
        return SlotInfo(planning_group=None, schedule="-", coaches=[], days=fallback_days)
    slot = summarize_planning_matches(matches, group.name)
    return replace(slot, days=slot.days or fallback_days)


# ---------------------------------------------------------------------------
# Writing a table
# ---------------------------------------------------------------------------

def _reset_cell(ws: Worksheet, row: int, column: int, clear_value: bool = True) -> None:
    cell = ws.cell(row=row, column=column)
    if clear_value:
        cell.value = None
    cell.fill = NO_FILL
    cell.border = NO_BORDER


def _write_title_block(ws: Worksheet, top: int, group: SheetGroup, slot: SlotInfo) -> None:
    """Group name, schedule, coaches and member count, over the template's header lines."""
    for row in range(top + 1, top + HEADER_LINES + 1):
        for column in range(1, LAST_CLEARED_COLUMN + 1):
            _reset_cell(ws, row, column)
    coaches = " / ".join(str(c).strip() for c in slot.coaches if str(c).strip()) or "Non renseigné"
    lines = [
        (group.name, FONT_TITLE, 24),
        (f"🕐 Horaire : {slot.schedule}", FONT_INFO, 16),
        (f"🧑‍🏫 Encadrants : {coaches}", FONT_INFO, 15),
        (f"👥 Total élèves : {len(group.members)}", FONT_TOTAL, 15),
    ]
    for offset, (text, font, height) in enumerate(lines, start=1):
        cell = ws.cell(row=top + offset, column=1, value=text)
        cell.font = font
        cell.alignment = ALIGN_LEFT
        ws.row_dimensions[top + offset].height = height
    ws.row_dimensions[top + HEADER_LINES].height = 6   # thin spacer before the table


def _style_header(cell: Any, align: Alignment) -> None:  # Any: openpyxl Cell or MergedCell
    cell.font = FONT_HEADER
    cell.fill = FILL_HEADER
    cell.alignment = align
    cell.border = BORDER_HEADER


def _write_column_headers(ws: Worksheet, header_row: int, layout: SheetLayout, dates: Sequence[datetime.date]) -> int:
    """Column headers (names, optional columns, one dd/mm column per session, or « Date »); returns the last column."""
    headers: list[tuple[int, str, int | None]] = [(1, "Prénom", None), (2, "Nom", None)]
    if layout.show_badges:
        headers += [(3, "Badge rouge", 12), (4, "Bloc", 8), (5, "Passeport Orange", 15)]
    if layout.authorization_column:
        headers.append((layout.authorization_column, "Autorisation", 13))
    if layout.health_column:
        headers.append((layout.health_column, "Santé", 7))
    for column, title, width in headers:
        _style_header(ws.cell(row=header_row, column=column, value=title), ALIGN_LEFT if column < 3 else ALIGN_CENTER)
        if width:
            ws.column_dimensions[get_column_letter(column)].width = width

    labels = [day.strftime("%d/%m") for day in dates] or ["Date"]
    for index, label in enumerate(labels):
        column = layout.first_date_column + index
        _style_header(ws.cell(row=header_row, column=column, value=label), ALIGN_CENTER)
        ws.column_dimensions[get_column_letter(column)].width = 5
    last_column = layout.first_date_column + len(labels) - 1
    for column in range(last_column + 1, LAST_CLEARED_COLUMN):
        _reset_cell(ws, header_row, column)
    return last_column


def _authorization_text(member: MemberRow) -> str | None:
    authorizations = []
    if str(member.get("parental_auth_autonomous") or "").strip() == "Oui":
        authorizations.append(PICTO_AUTONOME)
    if str(member.get("parental_auth_family") or "").strip() == "Oui":
        authorizations.append("Famille")
    return ", ".join(authorizations) or None


def _write_member_rows(ws: Worksheet, first_row: int, members: Sequence[MemberRow], layout: SheetLayout, last_column: int) -> int:
    """One zebra row per member, empty bordered cells under the session dates; returns the row after the last one."""
    row = first_row
    for member in members:
        values: list[tuple[int, object]] = [
            (1, str(member.get("first_name") or "").strip().capitalize()),
            (2, str(member.get("last_name") or "").strip().upper()),
        ]
        if layout.show_badges:
            values += [
                (3, str(member.get("badge_rouge", "Non")).strip()),
                (4, str(member.get("autonomie_bloc", "Non")).strip()),
                (5, "Oui" if "orange" in str(member.get("raw_passports") or "").lower() else "Non"),
            ]
        if layout.authorization_column:
            values.append((layout.authorization_column, _authorization_text(member)))
        health_pending = str(member.get("document_sante") or "").strip().upper() == "ATTENTE"
        if layout.health_column:
            values.append((layout.health_column, "✗" if health_pending else None))

        fill = FILL_ZEBRA if row % 2 == 0 else FILL_WHITE
        for column, value in values:
            cell = ws.cell(row=row, column=column, value=value)
            cell.font = FONT_HEALTH_PENDING if column == layout.health_column and health_pending else FONT_MEMBER
            cell.fill = fill
            cell.alignment = ALIGN_LEFT if column < 3 else ALIGN_CENTER
            cell.border = BORDER_CELL
        for column in range(layout.first_date_column, last_column + 1):
            cell = ws.cell(row=row, column=column)
            cell.fill = fill
            cell.border = BORDER_CELL
        for column in range(last_column + 1, LAST_CLEARED_COLUMN):
            _reset_cell(ws, row, column, clear_value=False)
        row += 1
    for empty_row in range(row, LAST_CLEARED_ROW + 1):
        for column in range(1, LAST_CLEARED_COLUMN):
            _reset_cell(ws, empty_row, column)
    return row


def _draw_table_borders(ws: Worksheet, header_row: int, last_row: int, layout: SheetLayout,
                        last_column: int, dates: Sequence[datetime.date]) -> None:
    """Thick black line before the first session and at each change of month, thick blue frame around the table."""
    month_ends = [layout.first_date_column + i for i in range(len(dates) - 1) if dates[i].month != dates[i + 1].month]
    for row in range(header_row, last_row + 1):
        for column in month_ends:
            cell = ws.cell(row=row, column=column)
            border = cell.border
            cell.border = Border(left=border.left or THIN_GRAY, right=MEDIUM_BLACK, top=border.top or THIN_GRAY, bottom=border.bottom or THIN_GRAY)
        cell = ws.cell(row=row, column=layout.first_date_column)
        cell.border = Border(left=MEDIUM_BLACK, right=cell.border.right, top=cell.border.top, bottom=cell.border.bottom)
    for row in range(header_row, last_row + 1):
        for column in range(1, last_column + 1):
            cell = ws.cell(row=row, column=column)
            border = cell.border
            cell.border = Border(
                left=THICK_BLUE if column == 1 else border.left,
                right=THICK_BLUE if column == last_column else border.right,
                top=THICK_BLUE if row == header_row else border.top,
                bottom=THICK_BLUE if row == last_row else border.bottom,
            )


def _group_qrcode(group: SheetGroup, slot: SlotInfo, planning: Sequence[PlanningItem]) -> str | None:
    """Cached WhatsApp QR code of the group, else one generated from the WhatsApp link of its planning slots."""
    cached = find_group_qrcode(slot.planning_group, group.lookup_name, group.name, *group.qrcode_names)
    if cached:
        return cached
    items = list(slot.items)
    if slot.planning_group:
        target = slot.planning_group.strip().lower()
        items += [item for item in planning if str(item.get("groupe") or "").strip().lower() == target and item not in items]
    for item in items:
        path = get_group_qrcode(str(item.get("whatsapp_link") or "").strip(), str(item.get("groupe") or "").strip())
        if path:
            return path
    logger.warning("Presence sheet: no WhatsApp QR code for %r (no WhatsApp link in the planning)", group.name)
    return None


def _add_qrcode(ws: Worksheet, path: str, anchor_row: int) -> bool:
    """QR code image under the table; a broken image only loses the QR code, not the sheet."""
    try:
        image = XLImage(path)
    except (OSError, ValueError):
        logger.warning("Presence sheet: unreadable QR code image %s", os.path.basename(path), exc_info=True)
        return False
    image.width = QR_SIZE_PX
    image.height = QR_SIZE_PX
    ws.add_image(image, f"A{anchor_row}")
    return True


def write_group_table(ws: Worksheet, top: int, group: SheetGroup, slot: SlotInfo, layout: SheetLayout,
                      dates: Sequence[datetime.date], planning: Sequence[PlanningItem]) -> TableExtent:
    """Writes one table, its header lines starting below row `top`, and the QR code two rows under it."""
    ws.sheet_view.showGridLines = False
    _write_title_block(ws, top, group, slot)
    header_row = top + HEADER_LINES + 1
    last_column = _write_column_headers(ws, header_row, layout, dates)
    next_row = _write_member_rows(ws, header_row + 1, group.members, layout, last_column)
    _draw_table_borders(ws, header_row, next_row - 1, layout, last_column, dates)

    qr_anchor_row = next_row + 1
    qr_path = _group_qrcode(group, slot, planning)
    has_qrcode = _add_qrcode(ws, qr_path, qr_anchor_row) if qr_path else False
    return TableExtent(
        header_row=header_row,
        last_member_row=next_row - 1,
        last_column=last_column,
        print_bottom_row=qr_anchor_row + QR_ROWS - 1 if has_qrcode else next_row - 1,
        next_table_offset=qr_anchor_row + QR_ROWS + STACKED_GAP_ROWS,
    )


# ---------------------------------------------------------------------------
# Page setup and files
# ---------------------------------------------------------------------------

def _set_a3_landscape(ws: Worksheet, print_area: str) -> None:
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = A3_PAPER
    ws.print_title_cols = "A:B"   # first and last names repeated when columns spill onto another page
    ws.print_area = print_area
    ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.4, bottom=0.4, header=0.2, footer=0.2)


def _fit_to_width(ws: Worksheet) -> None:
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0


def _set_single_table_print(ws: Worksheet, extent: TableExtent) -> None:
    """A3 landscape, one page wide unless that would print below MIN_READABLE_SCALE; column headers repeated."""
    width_units = sum(ws.column_dimensions[get_column_letter(c)].width or 8.43 for c in range(1, extent.last_column + 1))
    printable_width_mm = 420 - (0.3 + 0.3) * 25.4   # A3 landscape minus the side margins
    scale = int(printable_width_mm / (width_units * 2.05) * 100)   # one Excel width unit is about 2.05 mm
    if scale >= MIN_READABLE_SCALE:
        _fit_to_width(ws)
    else:
        ws.page_setup.scale = MIN_READABLE_SCALE
    _set_a3_landscape(ws, f"A1:{get_column_letter(extent.last_column)}{extent.print_bottom_row}")
    ws.print_title_rows = f"{extent.header_row}:{extent.header_row}"


def _load_template(template_file: str) -> tuple[Workbook, frozenset[tuple[str, str]]]:
    workbook = openpyxl.load_workbook(template_file)
    return workbook, template_formulas(workbook)   # member data must never become a formula


def _workbook_bytes(workbook: Workbook, keep_formulas: frozenset[tuple[str, str]]) -> bytes:
    neutralize_formulas(workbook, keep_formulas)
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def generate_presence_sheets(
    selected_groups: Sequence[str],
    members: Sequence[MemberRow],
    planning: Sequence[PlanningItem],
    *,
    variant: PresenceVariant,
    first_day: datetime.date | None = None,
    last_day: datetime.date | None = None,
    group_tarifs: Mapping[str, Sequence[str]] | None = None,
    show_health_col: bool = False,
    same_sheet: bool = False,
    today: datetime.date | None = None,
) -> list[PresenceFile]:
    """Attendance workbooks of the selected planning groups, in memory.

    `group_tarifs` maps a group to its HelloAsso tariffs (planning page); `show_health_col` adds a « Santé »
    column (✗ in red while the FFME health document is pending); `same_sheet` ("cours" only) stacks every table
    in one sheet. Raises FileNotFoundError when the template is missing."""
    template_file = template_path(TEMPLATE_NAME)
    if not os.path.exists(template_file):
        raise FileNotFoundError(f"Presence sheet template not found: {template_file}")
    layout = SheetLayout.for_variant(variant, show_health_col)
    groups = sheet_groups(selected_groups, members, variant, group_tarifs or {}, today or datetime.date.today())
    if not groups:
        return []

    def table(ws: Worksheet, top: int, group: SheetGroup) -> TableExtent:
        slot = resolve_slot(group, planning)
        return write_group_table(ws, top, group, slot, layout, session_dates(slot.days, first_day, last_day), planning)

    if same_sheet and variant == "cours":
        workbook, keep_formulas = _load_template(template_file)
        ws = workbook.active
        top, last_column, print_bottom = 0, 0, 0
        for index, group in enumerate(groups):
            if index:
                ws.row_breaks.append(Break(id=top))   # each table starts on a new printed page
            extent = table(ws, top, group)
            last_column = max(last_column, extent.last_column)
            print_bottom = max(print_bottom, extent.print_bottom_row)
            top = extent.next_table_offset
        _fit_to_width(ws)
        _set_a3_landscape(ws, f"A1:{get_column_letter(last_column)}{print_bottom}")
        logger.info("Presence sheets: %d tables stacked in one sheet", len(groups))
        return [PresenceFile(STACKED_FILENAME, _workbook_bytes(workbook, keep_formulas))]

    files = []
    for group in groups:
        workbook, keep_formulas = _load_template(template_file)
        _set_single_table_print(workbook.active, table(workbook.active, 0, group))
        files.append(PresenceFile(f"Feuille_Presence_{clean_filename(group.name)}.xlsx", _workbook_bytes(workbook, keep_formulas)))
    logger.info("Presence sheets: %d file(s) generated", len(files))
    return files
