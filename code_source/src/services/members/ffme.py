"""FFME: the federal CSV export of the season's members, and the import of the MyFFME licensee list (Excel) matched
against the members, by licence number then by name.

Knows nothing about HTTP: refusals are raised as domain.errors.
"""

from __future__ import annotations

import datetime
import io
import logging
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import openpyxl

from domain.errors import InvalidRequest
from domain.members.sex import parse_sex
from domain.members.view import is_cancelled
from domain.utils import clean_digits_only, is_missing, normalize_name
from exports.membership_excel import ffme_csv_bytes, parse_date_to_datetime
from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.ffme_import import FfmeImportRepository, FfmeMatch, MemberForMatching
from infrastructure.sqlite.members import MemberRepository

logger = logging.getLogger("alj")

# Shown to the office (the cause goes to the logs only)
UNREADABLE_EXCEL = "Fichier Excel illisible : vérifiez qu'il s'agit bien de l'export .xlsx des licenciés MyFFME."
MATCHING_FAILED = "Erreur lors du rapprochement FFME (détails dans les journaux)."
NOTHING_TO_APPLY = "Aucune mise à jour à appliquer (aucun rapprochement trouvé)."

LAST_NAME, FIRST_NAME, LICENCE = "Nom", "Prénom", "N° de licence"
REQUIRED_COLUMNS = (LAST_NAME, FIRST_NAME, LICENCE)
HEALTH_DOCUMENT = "Document de santé"
STATUS_DONE = "Terminé"


# One row of the licensee sheet: column header -> cell value (text, number, date or None)
LicenseeRow = Dict[str, object]


class LicenseeSheet(TypedDict):
    columns: List[str]
    rows: List[LicenseeRow]


class MatchStats(TypedDict):
    total_processed: int
    matched_by_licence: int
    matched_by_name: int
    errors: List[str]


class UnmatchedLicensee(TypedDict):
    nom: str
    prenom: str
    licence: str
    birth_date: str
    passeports: str
    diplomes: str
    document_sante: str


class FfmePreparation(TypedDict):
    """The file matched against the members, nothing written."""
    updates: List[FfmeMatch]
    unmatched: List[UnmatchedLicensee]
    users: List[MemberForMatching]  # every member, for the office's manual matches
    stats: MatchStats


class ExportStats(TypedDict):
    produced_count: int
    termine_count: int
    ignored_count: int
    estimated_total: int
    renewals_count: int
    new_licences_count: int
    ignored_details: List[str]


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def export_csv(season: str, include_termine: bool) -> bytes:
    return ffme_csv_bytes(MemberRepository.list_flat_member_rows(season), include_termine=include_termine)


def export_stats(season: str) -> ExportStats:
    """What export_csv would declare for the season, with the rules of generate_ffme_csv: members left out
    (waiting list, nothing paid unless added by hand, cancelled, missing birth date, missing sex on a first licence),
    already done ('Terminé'), renewals and first licences."""
    produced_count = ignored_count = done_count = renewals_count = new_licences_count = 0
    ignored_details: List[str] = []
    now = datetime.datetime.now()

    for member in MemberRepository.list_flat_member_rows(season):
        tariff_name = str(member.get("tarif_name") or "").lower()
        status = str(member.get("status") or "").lower()
        added_by_hand = "ajout manuel" in str(member.get("commentaires_correctif") or "").lower()
        if "attente" in tariff_name or (member.get("amount", 0.0) == 0.0 and not added_by_hand) or is_cancelled(status):
            ignored_count += 1
            continue

        name = f"{str(member.get('last_name') or 'Inconnu').strip().upper()} {str(member.get('first_name') or 'Inconnu').strip()}"
        birth_date = _birth_date(member)
        if not birth_date or birth_date >= now:
            ignored_count += 1
            ignored_details.append(f"{name} (date de naissance manquante/invalide)")
            continue

        # Sex: required for a first licence (same rule as generate_ffme_csv)
        is_renewal = 5 <= len(clean_digits_only(member.get("licence_ffme") or "")) <= 10
        if not is_renewal and parse_sex(member.get("sex")) is None:
            ignored_count += 1
            ignored_details.append(f"{name} (sexe non renseigné)")
            continue

        if "termin" in status:
            done_count += 1
        else:
            produced_count += 1
        if is_renewal:
            renewals_count += 1
        else:
            new_licences_count += 1

    return ExportStats(
        produced_count=produced_count,
        termine_count=done_count,
        ignored_count=ignored_count,
        estimated_total=produced_count + done_count,
        renewals_count=renewals_count,
        new_licences_count=new_licences_count,
        ignored_details=ignored_details[:20],
    )


def _birth_date(member: Dict[str, Any]) -> Optional[datetime.datetime]:  # Any: a row of the member read model
    value = member.get("birth_date") or member.get("champ_Date de naissance de l'adhérent") or ""
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    parsed = parse_date_to_datetime(str(value).strip())
    return parsed if isinstance(parsed, datetime.datetime) else None


# --------------------------------------------------------------------------
# Import of the MyFFME licensee list
# --------------------------------------------------------------------------
def prepare_licensees(excel_content: bytes) -> FfmePreparation:
    """Phase A of the import: reads the MyFFME Excel export and matches each licensee with a member, by licence
    number then by name. Writes nothing; problems are listed in stats.errors."""
    preparation = FfmePreparation(updates=[], unmatched=[], users=[],
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
        members_by_licence = {}
        members_by_name = {}
        for member in members:
            licence = clean_digits_only(member["licence_ffme"])
            if licence:
                members_by_licence[licence] = member
            name_key = (normalize_name(member["last_name"]), normalize_name(member["first_name"]))
            if all(name_key):
                members_by_name[name_key] = member

        has_health_column = HEALTH_DOCUMENT in sheet["columns"]
        for row in sheet["rows"]:
            stats["total_processed"] += 1
            last_name = _cell_text(row, LAST_NAME)
            first_name = _cell_text(row, FIRST_NAME)
            licence = clean_digits_only(row.get(LICENCE))
            if not licence:
                licence = clean_digits_only(formula_licences.get((last_name, first_name), ""))

            matched: Optional[MemberForMatching] = members_by_licence.get(licence) if licence else None
            if matched:
                stats["matched_by_licence"] += 1
            elif last_name and first_name:
                matched = members_by_name.get((normalize_name(last_name), normalize_name(first_name)))
                if matched:
                    stats["matched_by_name"] += 1

            health_document = _cell_text(row, HEALTH_DOCUMENT) if has_health_column else ""
            if matched:
                # The file's (cleaned) licence number wins; the member's is kept only when the file has none
                final_licence = licence or clean_digits_only(matched["licence_ffme"])
                preparation["updates"].append((
                    STATUS_DONE, final_licence, _cell_text(row, "Passeports"), _cell_text(row, "Diplômes"), health_document, matched["id"]))
            else:
                preparation["unmatched"].append(UnmatchedLicensee(
                    nom=last_name, prenom=first_name, licence=licence,
                    birth_date=_cell_text(row, "Date de naissance"),
                    passeports=_cell_text(row, "Passeports"),
                    diplomes=_cell_text(row, "Diplômes"),
                    document_sante=health_document,
                ))
    except Exception:  # reported to the office as a fixed message; the cause (SQL, data) goes to the logs
        logger.exception("FFME import: matching failed")
        stats["errors"].append(MATCHING_FAILED)
    return preparation


def apply_import(season: str, excel_content: Optional[bytes], manual_matches: List[FfmeMatch]) -> Tuple[int, MatchStats]:
    """Phase B: writes the file's automatic matches (computed again, as in the preview) and the office's manual
    matches. Returns the number of members updated and the matching statistics. InvalidRequest when nothing applies."""
    updates: List[FfmeMatch] = []
    stats = MatchStats(total_processed=0, matched_by_licence=0, matched_by_name=0, errors=[])
    if excel_content is not None:
        preparation = prepare_licensees(excel_content)
        updates, stats = list(preparation["updates"]), preparation["stats"]
    updates.extend(manual_matches)
    if not updates:
        raise InvalidRequest((stats["errors"] or [NOTHING_TO_APPLY])[0])
    if not CloudDatabase.is_enabled():  # a local database of its own: keep a copy before the import changes it
        SqliteDatabase.create_db_backup()
    FfmeImportRepository.apply_ffme_matches(updates, season_name=season)
    return len(updates), stats


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
        return LicenseeSheet(columns=[], rows=[])
    columns = [str(header).strip() if header is not None else "" for header in values[header_index]]
    # strict=False: a row may stop before the last column (empty trailing cells)
    rows = [dict(zip(columns, row, strict=False)) for row in values[header_index + 1:] if any(not is_missing(cell) for cell in row)]
    return LicenseeSheet(columns=columns, rows=rows)


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


def _cell_text(row: LicenseeRow, column: str) -> str:
    value = row.get(column)
    if is_missing(value):
        return ""
    return value.strftime("%d/%m/%Y") if hasattr(value, "strftime") else str(value).strip()
