"""Export Excel de la liste des compétiteurs d'une compétition selon la charte graphique du club.

Charte graphique ALJ Escalade :
- Police : Segoe UI
- En-têtes : Bleu foncé #1E3A8A avec texte blanc gras
- Lignes : Lignes zébrées alternées (#FFFFFF et #F8FAFC)
- Bordures : Quadrillage fin et quadrillage actif à l'impression
"""

from __future__ import annotations

import io
from typing import Any, Dict, List, Mapping

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from domain.competitions.models import LIBELLES_STATUT_PAIEMENT, PaymentStatus
from domain.utils import format_amount
from exports.spreadsheet_safety import neutralize_formulas

HEADER_BG = "1E3A8A"
ZEBRA_BG = "F8FAFC"
WHITE_BG = "FFFFFF"

FONT_NAME = "Segoe UI"
FONT_TITLE = Font(name=FONT_NAME, size=14, bold=True, color="1E3A8A")
FONT_META = Font(name=FONT_NAME, size=10, italic=True, color="475569")
FONT_HEADER = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
FONT_DATA = Font(name=FONT_NAME, size=10)
FONT_DATA_BOLD = Font(name=FONT_NAME, size=10, bold=True)

FILL_HEADER = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
FILL_ZEBRA = PatternFill(start_color=ZEBRA_BG, end_color=ZEBRA_BG, fill_type="solid")
FILL_WHITE = PatternFill(start_color=WHITE_BG, end_color=WHITE_BG, fill_type="solid")

THIN_SIDE = Side(border_style="thin", color="CBD5E1")
BORDER_THIN = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

COLUMNS = [
    "Nom",
    "Prénom",
    "Catégorie",
    "Surclassement",
    "Discipline",
    "Statut",
    "Paiement",
    "Date de naissance",
    "Numéro de licence",
    "Email",
    "Téléphone",
]


def payment_label(participant: Mapping[str, Any]) -> str:
    """« Payé (15,50 €) », « En attente », « Annulé — perdu »… (labels of the domain model)."""
    status = str(participant.get("statut_paiement") or PaymentStatus.NON_INVITE)
    label = LIBELLES_STATUT_PAIEMENT.get(status, status)
    amount = format_amount(participant.get("montant_paye")) if participant.get("montant_paye") else ""
    return f"{label} ({amount} €)" if amount else label


HEADER_ROW = 4  # rows 1-2: competition title and details
CENTERED_COLUMNS = (3, 4, 6, 7, 8, 9)  # Catégorie, Surclassement, Statut, Paiement, Date de naissance, Licence


def _write_title(sheet: Worksheet, comp: Mapping[str, Any]) -> None:
    """Rows 1-2: the competition's name, then its dates, venue and discipline."""
    start_date = comp.get("date_competition") or ""
    end_date = comp.get("date_fin") or start_date
    venue = comp.get("lieu") or ""
    discipline = comp.get("type") or ""
    details = [f"Date : {start_date}" if not end_date or end_date == start_date else f"Dates : {start_date} au {end_date}"]
    if venue:
        details.append(f"Lieu : {venue}")
    if discipline:
        details.append(f"Discipline : {discipline}")
    sheet.cell(row=1, column=1, value=f"ALJ Escalade — {comp.get('nom') or 'Compétition'}").font = FONT_TITLE
    sheet.cell(row=2, column=1, value=" · ".join(details)).font = FONT_META


def _competitor_values(participant: Mapping[str, Any], default_discipline: str) -> list[str]:
    """The cells of one competitor, in the order of COLUMNS."""
    return [
        str(participant.get("nom") or "").strip().upper(),
        str(participant.get("prenom") or "").strip().title(),
        str(participant.get("categorie_ffme") or participant.get("categorie") or "").strip(),
        "Oui" if participant.get("surclassement") else "Non",
        str(participant.get("discipline") or participant.get("creneau_groupe") or default_discipline or "").strip(),
        "Sélectionné" if participant.get("selectionne") else "Non invité",
        payment_label(participant),
        str(participant.get("date_naissance") or participant.get("birth_date") or "").strip(),
        str(participant.get("num_licence") or participant.get("licence_ffme") or "").strip(),
        str(participant.get("email") or "").strip(),
        str(participant.get("phone") or participant.get("telephone") or "").strip(),
    ]


def _write_competitors(sheet: Worksheet, participants: List[Dict[str, Any]], default_discipline: str) -> None:
    """The header row, then one zebra row per competitor (the name in bold)."""
    for column, title in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=column, value=title)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_THIN
    for index, participant in enumerate(participants):
        row = HEADER_ROW + 1 + index
        fill = FILL_ZEBRA if index % 2 == 1 else FILL_WHITE
        for column, value in enumerate(_competitor_values(participant, default_discipline), start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            cell.font = FONT_DATA_BOLD if column == 1 else FONT_DATA
            cell.fill = fill
            cell.border = BORDER_THIN
            cell.alignment = (Alignment(horizontal="center", vertical="center") if column in CENTERED_COLUMNS
                              else Alignment(vertical="center"))


def _autosize_columns(sheet: Worksheet) -> None:
    """Each column as wide as its longest value from the header row down (12 at least)."""
    for column in sheet.columns:
        longest = max((len(str(cell.value or "")) for cell in column if cell.row >= HEADER_ROW), default=0)
        sheet.column_dimensions[get_column_letter(column[0].column)].width = max(longest + 4, 12)


def export_competitors_excel(comp: Mapping[str, Any], participants: List[Dict[str, Any]] | None = None) -> bytes:
    """Génère le classeur Excel d'une compétition avec ses compétiteurs et retourne les octets."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Compétiteurs"
    # Gridlines shown and printed, landscape A4
    sheet.sheet_view.showGridLines = True
    sheet.page_setup.printGridlines = True
    sheet.page_setup.orientation = sheet.ORIENTATION_LANDSCAPE
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4

    _write_title(sheet, comp)
    rows = participants if participants is not None else (comp.get("participants") or [])
    _write_competitors(sheet, rows, comp.get("type") or "")
    _autosize_columns(sheet)

    neutralize_formulas(workbook)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
