"""FFME: the federal CSV export of the season's members, and the import of the MyFFME licensee list (Excel) matched
against the members, by licence number then by name, checked against the birth date.

Knows nothing about HTTP: refusals are raised as domain.errors.
"""

from __future__ import annotations

import datetime
import io
import logging
from collections import Counter
from typing import Collection, Dict, List, Literal, Optional, Sequence, Set, Tuple, TypedDict

import openpyxl

from domain.errors import InvalidRequest
from domain.members.age_rules import parse_birth_date
from domain.members.ffme_changes import FieldChange, FileValues, MemberState, MemberWrite, SeasonPurchase, plan_member_changes
from domain.utils import clean_digits_only, is_missing, normalize_name
from exports.membership_excel import check_ffme_member, ffme_csv_bytes, is_termine
from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.ffme_import import FfmeImportRepository, MemberForMatching
from infrastructure.sqlite.members import MemberRepository

logger = logging.getLogger("alj")

# Shown to the office (the cause goes to the logs only)
UNREADABLE_EXCEL = "Fichier Excel illisible : vérifiez qu'il s'agit bien de l'export .xlsx des licenciés MyFFME."
MATCHING_FAILED = "Erreur lors du rapprochement FFME (détails dans les journaux)."
NOTHING_TO_APPLY = "Aucune mise à jour à appliquer (aucun rapprochement trouvé)."
DUPLICATE_MATCH = "Importation refusée : {name} est rapproché par plusieurs lignes du fichier, n'en gardez qu'une."
UNKNOWN_MANUAL_MATCH = "Association manuelle impossible : ligne {row_number} du fichier déjà rapprochée ou adhérent introuvable."

LAST_NAME, FIRST_NAME, LICENCE = "Nom", "Prénom", "N° de licence"
REQUIRED_COLUMNS = (LAST_NAME, FIRST_NAME, LICENCE)
HEALTH_DOCUMENT = "Document de santé"
# The health document column holds QS, COMPETITION, LOISIR (valid: the member may climb) or ATTENTE; MyFFME leaves
# the cell empty while nothing was received
HEALTH_DOCUMENT_PENDING = "ATTENTE"
BIRTH_DATE = "Date de naissance"


# One row of the licensee sheet: column header -> cell value (text, number, date or None)
LicenseeRow = Dict[str, object]


class LicenseeSheet(TypedDict):
    columns: List[str]
    rows: List[LicenseeRow]
    row_numbers: List[int]  # the Excel line of each row


class MatchStats(TypedDict):
    total_processed: int
    matched_by_licence: int
    matched_by_name: int
    errors: List[str]


class Licensee(TypedDict):
    """A row of the file: its Excel line and its values (text)."""
    row_number: int
    nom: str
    prenom: str
    licence: str
    birth_date: str
    passeports: str
    diplomes: str
    document_sante: str


class ManualMatch(TypedDict):
    """A row left unmatched (row_number: its Excel line), linked by the office to a member."""
    row_number: int
    user_id: int


MatchSource = Literal["licence", "nom", "manuel"]


class PlannedRow(TypedDict):
    """A matched row of the file and what the import changes on its member (domain.members.ffme_changes)."""
    row_number: int
    member: MemberForMatching
    source: MatchSource
    changes: List[FieldChange]
    no_active_registration: bool
    duplicate: bool  # its member is matched by another row too
    licence_conflict: str  # "LAST First" of another member holding the file's licence (a sibling's, typed by mistake)
    write: MemberWrite


class FfmePreparation(TypedDict):
    """The file matched against the members and the changes planned, nothing written."""
    rows: List[PlannedRow]
    unmatched: List[Licensee]
    users: List[MemberForMatching]  # every member, for the office's manual matches
    stats: MatchStats


class ExportStats(TypedDict):
    ignored_count: int
    estimated_total: int
    renewals_count: int
    new_licences_count: int
    ignored_details: List[str]
    to_check_details: List[str]


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def export_csv(season: str, include_termine: bool) -> bytes:
    return ffme_csv_bytes(MemberRepository.list_flat_member_rows(season), include_termine=include_termine)


def export_stats(season: str, include_termine: bool) -> ExportStats:
    """What export_csv would declare for the season with the same option, by the export's own rules (check_ffme_member):
    members left out (waiting list, nothing paid unless added by hand, cancelled, missing birth date, missing sex or
    unknown country / nationality on a first licence), renewals and first licences, and the values exported empty that
    the office should correct. Members already declared ('Terminé') are not counted at all when they are not included."""
    exported_count = ignored_count = renewals_count = new_licences_count = 0
    ignored_details: List[str] = []
    to_check_details: List[str] = []

    for member in MemberRepository.list_flat_member_rows(season):
        if not include_termine and is_termine(member):
            continue
        check = check_ffme_member(member, include_termine)
        if check is None:
            ignored_count += 1
            continue
        if check.row is None:
            ignored_count += 1
            ignored_details.append(f"{check.label} ({check.left_out_reason})")
            continue
        to_check_details.extend(f"{check.label} ({item})" for item in check.to_check)

        exported_count += 1
        if check.is_renewal:
            renewals_count += 1
        else:
            new_licences_count += 1

    return ExportStats(
        ignored_count=ignored_count,
        estimated_total=exported_count,
        renewals_count=renewals_count,
        new_licences_count=new_licences_count,
        ignored_details=ignored_details[:20],
        to_check_details=to_check_details[:20],
    )


# --------------------------------------------------------------------------
# Import of the MyFFME licensee list
# --------------------------------------------------------------------------
def prepare_licensees(excel_content: bytes, season: str, manual_matches: Sequence[ManualMatch] = ()) -> FfmePreparation:
    """Phase A of the import: reads the MyFFME Excel export and matches each licensee with a member, by licence
    number then by name; a known birth date of the file that disagrees with the member's rules the match out. Plans
    the changes of every matched row (and of the office's manual matches) on the season. Writes nothing; problems are
    listed in stats.errors."""
    preparation = FfmePreparation(rows=[], unmatched=[], users=[],
                                  stats=MatchStats(total_processed=0, matched_by_licence=0, matched_by_name=0, errors=[]))
    stats = preparation["stats"]
    try:
        sheet = _read_licensee_sheet(excel_content)
    except Exception:  # openpyxl and zipfile raise many types on a damaged or foreign file
        logger.exception("FFME import: Excel file unreadable")
        stats["errors"].append(UNREADABLE_EXCEL)
        return preparation
    missing = [column for column in REQUIRED_COLUMNS if column not in sheet["columns"]]
    if missing:
        stats["errors"].append(f"Colonne requise manquante dans le fichier Excel : {missing[0]}")
        return preparation

    try:
        formula_licences = _formula_licences(excel_content)
        members = FfmeImportRepository.list_members_for_matching()
        preparation["users"] = members
        members_by_licence: Dict[str, MemberForMatching] = {}
        members_by_name: Dict[Tuple[str, str], List[MemberForMatching]] = {}  # homonyms included
        for member in members:
            licence = clean_digits_only(member["licence_ffme"])
            if licence:
                members_by_licence[licence] = member
            name_key = (normalize_name(member["last_name"]), normalize_name(member["first_name"]))
            if all(name_key):
                members_by_name.setdefault(name_key, []).append(member)

        purchases = FfmeImportRepository.list_season_purchases(season)
        has_health_column = HEALTH_DOCUMENT in sheet["columns"]
        matched_rows: List[Tuple[Licensee, MemberForMatching, MatchSource]] = []
        for row_number, row in zip(sheet["row_numbers"], sheet["rows"], strict=True):
            stats["total_processed"] += 1
            last_name = _cell_text(row, LAST_NAME)
            first_name = _cell_text(row, FIRST_NAME)
            licence = clean_digits_only(row.get(LICENCE))
            if not licence:
                licence = clean_digits_only(formula_licences.get((last_name, first_name), ""))

            birth_date = parse_birth_date(row.get(BIRTH_DATE))
            source: MatchSource = "licence"
            matched: Optional[MemberForMatching] = members_by_licence.get(licence) if licence else None
            # A licence given to the wrong member (a sibling's, typed on HelloAsso) is not trusted: the name decides
            if matched and not _birth_dates_agree(birth_date, matched):
                matched = None
            if matched:
                stats["matched_by_licence"] += 1
            elif last_name and first_name:
                homonyms = members_by_name.get((normalize_name(last_name), normalize_name(first_name)), [])
                matched = _match_by_birth_date(homonyms, birth_date)
                source = "nom"
                if matched:
                    stats["matched_by_name"] += 1

            licensee = Licensee(
                row_number=row_number, nom=last_name, prenom=first_name, licence=licence,
                birth_date=_cell_text(row, BIRTH_DATE),
                passeports=_cell_text(row, "Passeports"),
                diplomes=_cell_text(row, "Diplômes"),
                document_sante=(_cell_text(row, HEALTH_DOCUMENT) or HEALTH_DOCUMENT_PENDING) if has_health_column else "",
            )
            if matched:
                matched_rows.append((licensee, matched, source))
            else:
                preparation["unmatched"].append(licensee)

        members_by_id = {member["id"]: member for member in members}
        unmatched_by_row = {licensee["row_number"]: licensee for licensee in preparation["unmatched"]}
        for manual in manual_matches:
            linked_licensee = unmatched_by_row.pop(manual["row_number"], None)
            linked_member = members_by_id.get(manual["user_id"])
            if linked_licensee is None or linked_member is None:
                raise InvalidRequest(UNKNOWN_MANUAL_MATCH.format(row_number=manual["row_number"]))
            matched_rows.append((linked_licensee, linked_member, "manuel"))
        preparation["unmatched"] = list(unmatched_by_row.values())
        preparation["rows"] = [_planned_row(licensee, member, source, purchases.get(member["id"], []),
                                            members_by_licence.get(licensee["licence"]))
                               for licensee, member, source in matched_rows]
        duplicates = _duplicate_user_ids(preparation["rows"])
        for planned in preparation["rows"]:
            planned["duplicate"] = planned["member"]["id"] in duplicates
    except InvalidRequest:
        raise
    except Exception:  # reported to the office as a fixed message; the cause (SQL, data) goes to the logs
        logger.exception("FFME import: matching failed")
        stats["errors"].append(MATCHING_FAILED)
    return preparation


def is_listed(row: PlannedRow) -> bool:
    """Shown by the preview: the row changes something, or needs the office's attention."""
    return bool(row["changes"]) or row["no_active_registration"] or row["duplicate"] or bool(row["licence_conflict"])


def apply_import(season: str, excel_content: bytes, manual_matches: Sequence[ManualMatch] = (),
                 excluded_rows: Collection[int] = ()) -> Tuple[int, MatchStats]:
    """Phase B: writes the changes planned for the file's automatic matches (computed again, as in the preview) and
    the office's manual matches, except the rows the office left out (Excel lines). Returns the number of members
    changed and the matching statistics. InvalidRequest when nothing matched, or when a member is still matched by
    several rows."""
    preparation = prepare_licensees(excel_content, season, manual_matches)
    stats = preparation["stats"]
    if not preparation["rows"]:
        raise InvalidRequest((stats["errors"] or [NOTHING_TO_APPLY])[0])
    rows = [row for row in preparation["rows"] if row["row_number"] not in excluded_rows]
    duplicates = _duplicate_user_ids(rows)
    if duplicates:
        member = next(row["member"] for row in rows if row["member"]["id"] in duplicates)
        raise InvalidRequest(DUPLICATE_MATCH.format(name=f"{member['last_name']} {member['first_name']}"))
    writes = [row["write"] for row in rows if row["changes"]]
    if writes and not CloudDatabase.is_enabled():  # a local database of its own: keep a copy before the import changes it
        SqliteDatabase.create_db_backup()
    FfmeImportRepository.apply_ffme_matches(writes)
    return len(writes), stats


def _duplicate_user_ids(rows: List[PlannedRow]) -> Set[int]:
    """The members matched by several rows."""
    counts = Counter(row["member"]["id"] for row in rows)
    return {user_id for user_id, count in counts.items() if count > 1}


def _planned_row(licensee: Licensee, member: MemberForMatching, source: MatchSource, purchases: List[SeasonPurchase],
                 licence_holder: Optional[MemberForMatching]) -> PlannedRow:
    plan = plan_member_changes(
        member["id"],
        FileValues(licence=licensee["licence"], passports=licensee["passeports"], diplomas=licensee["diplomes"],
                   health_document=licensee["document_sante"]),
        MemberState(licence=member["licence_ffme"], passports=member["raw_passports"], diplomas=member["raw_diplomas"],
                    purchases=purchases),
    )
    return PlannedRow(row_number=licensee["row_number"], member=member, source=source, changes=plan["changes"],
                      no_active_registration=plan["no_active_registration"], duplicate=False, write=plan["write"],
                      licence_conflict=_licence_conflict(member, licence_holder))


def _licence_conflict(member: MemberForMatching, licence_holder: Optional[MemberForMatching]) -> str:
    """The other member already holding the row's licence, for the office to correct by hand (never cleared here: the
    stored number may be the right one)."""
    if licence_holder is None or licence_holder["id"] == member["id"]:
        return ""
    return f"{licence_holder['last_name']} {licence_holder['first_name']}"


def _read_licensee_sheet(excel_content: bytes) -> LicenseeSheet:
    """The licensee table (cached values, not formulas); MyFFME exports sometimes put a title row above the header."""
    workbook = openpyxl.load_workbook(io.BytesIO(excel_content), read_only=True, data_only=True)
    try:
        values = [list(row) for row in workbook.active.iter_rows(values_only=True)]
    finally:
        workbook.close()
    first_row_header = _sheet_from_rows(values, header_index=0)
    if all(column in first_row_header["columns"] for column in REQUIRED_COLUMNS):
        return first_row_header
    second_row_header = _sheet_from_rows(values, header_index=1)
    if all(column in second_row_header["columns"] for column in REQUIRED_COLUMNS):
        return second_row_header
    return first_row_header  # its missing column is reported


def _sheet_from_rows(values: List[List[object]], header_index: int) -> LicenseeSheet:
    if len(values) <= header_index:
        return LicenseeSheet(columns=[], rows=[], row_numbers=[])
    columns = [str(header).strip() if header is not None else "" for header in values[header_index]]
    sheet = LicenseeSheet(columns=columns, rows=[], row_numbers=[])
    for index in range(header_index + 1, len(values)):
        if any(not is_missing(cell) for cell in values[index]):
            # strict=False: a row may stop before the last column (empty trailing cells)
            sheet["rows"].append(dict(zip(columns, values[index], strict=False)))
            sheet["row_numbers"].append(index + 1)
    return sheet


def _formula_licences(excel_content: bytes) -> Dict[Tuple[str, str], str]:
    """Licence numbers by (last name, first name), read as formula text. Recent MyFFME exports store the licence
    column as a formula ('="636947"') without a cached value, which the cached-value reading sees as empty."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(excel_content), read_only=True, data_only=False)
        rows = list(workbook.active.iter_rows(values_only=True))
        workbook.close()
    except Exception:  # only a fallback: the cached-value reading stands alone
        logger.debug("Relecture des formules de l'export FFME impossible", exc_info=True)
        return {}
    if not rows:
        return {}
    headers = [str(header or "").strip() for header in rows[0]]
    if LICENCE not in headers:
        return {}
    column = headers.index(LICENCE)
    licences = {}
    for row in rows[1:]:
        last_name = str(row[0] or "").strip() if len(row) > 0 else ""
        first_name = str(row[1] or "").strip() if len(row) > 1 else ""
        value = row[column] if column < len(row) else None
        licences[(last_name, first_name)] = "" if value is None else str(value)
    return licences


def _birth_dates_agree(birth_date: Optional[datetime.date], member: MemberForMatching) -> bool:
    """False only when the file's birth date and the member's are both known and differ."""
    member_birth_date = parse_birth_date(member["birth_date"])
    return birth_date is None or member_birth_date is None or member_birth_date == birth_date


def _match_by_birth_date(homonyms: List[MemberForMatching], birth_date: Optional[datetime.date]) -> Optional[MemberForMatching]:
    """The only member of the same name whose birth date agrees with the file's (an equal one wins over an unknown
    one); None when none or several remain, left to the office's manual matching."""
    agreeing = [member for member in homonyms if _birth_dates_agree(birth_date, member)]
    same_birth_date = [member for member in agreeing if birth_date is not None and parse_birth_date(member["birth_date"]) == birth_date]
    candidates = same_birth_date or agreeing
    return candidates[0] if len(candidates) == 1 else None


def _cell_text(row: LicenseeRow, column: str) -> str:
    value = row.get(column)
    if is_missing(value):
        return ""
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else str(value).strip()
