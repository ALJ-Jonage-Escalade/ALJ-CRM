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

from domain.competitions.models import LIBELLES_STATUT_PAIEMENT, PAIEMENT_NON_INVITE
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


def payment_label(participant: Dict[str, Any]) -> str:
    """« Payé (15,50 €) », « En attente », « Annulé — perdu »… (labels of the domain model)."""
    status = str(participant.get("statut_paiement") or PAIEMENT_NON_INVITE)
    label = LIBELLES_STATUT_PAIEMENT.get(status, status)
    amount = format_amount(participant.get("montant_paye")) if participant.get("montant_paye") else ""
    return f"{label} ({amount} €)" if amount else label


def export_competitors_excel(comp: Mapping[str, Any], participants: List[Dict[str, Any]] | None = None) -> bytes:
    """Génère le classeur Excel d'une compétition avec ses compétiteurs et retourne les octets."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Compétiteurs"

    # Propriétés de vue et impression (quadrillage activé)
    ws.sheet_view.showGridLines = True
    ws.page_setup.printGridlines = True
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4

    # 1. En-tête de la compétition
    nom_comp = comp.get("nom") or "Compétition"
    date_comp = comp.get("date_competition") or ""
    date_fin = comp.get("date_fin") or date_comp
    lieu = comp.get("lieu") or ""
    disc = comp.get("type") or ""

    date_str = f"Date : {date_comp}" if not date_fin or date_fin == date_comp else f"Dates : {date_comp} au {date_fin}"
    meta_parts = [date_str]
    if lieu:
        meta_parts.append(f"Lieu : {lieu}")
    if disc:
        meta_parts.append(f"Discipline : {disc}")

    ws.cell(row=1, column=1, value=f"ALJ Escalade — {nom_comp}").font = FONT_TITLE
    ws.cell(row=2, column=1, value=" · ".join(meta_parts)).font = FONT_META

    # 2. Ligne des titres de colonnes (Ligne 4)
    start_row = 4
    for col_idx, col_name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=col_name)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER_THIN

    # 3. Données des compétiteurs
    parts = participants if participants is not None else (comp.get("participants") or [])
    current_row = start_row + 1

    for row_idx, p in enumerate(parts):
        is_zebra = row_idx % 2 == 1
        fill = FILL_ZEBRA if is_zebra else FILL_WHITE

        # Formatage des données
        nom = str(p.get("nom") or "").strip().upper()
        prenom = str(p.get("prenom") or "").strip().title()
        cat = str(p.get("categorie_ffme") or p.get("categorie") or "").strip()
        surclass = "Oui" if p.get("surclassement") else "Non"
        discipline_val = str(p.get("discipline") or p.get("creneau_groupe") or disc or "").strip()
        statut = "Sélectionné" if p.get("selectionne") else "Non invité"
        paiement = payment_label(p)
        dob = str(p.get("date_naissance") or p.get("birth_date") or "").strip()
        licence = str(p.get("num_licence") or p.get("licence_ffme") or "").strip()
        email = str(p.get("email") or "").strip()
        phone = str(p.get("phone") or p.get("telephone") or "").strip()

        row_values = [
            nom,
            prenom,
            cat,
            surclass,
            discipline_val,
            statut,
            paiement,
            dob,
            licence,
            email,
            phone,
        ]

        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=val)
            cell.font = FONT_DATA_BOLD if col_idx == 1 else FONT_DATA
            cell.fill = fill
            cell.border = BORDER_THIN
            if col_idx in (3, 4, 6, 7, 8, 9):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(vertical="center")

        current_row += 1

    # 4. Ajustement automatique de la largeur des colonnes
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if cell.row < start_row:
                continue
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    neutralize_formulas(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
