"""Génération du PDF / document imprimable de la liste des compétiteurs d'une compétition.

Respecte la charte graphique ALJ Escalade :
- Police : Segoe UI
- En-tête : #1E3A8A
- Lignes zébrées
- Prêt à l'impression (format paysage A4)
"""

from __future__ import annotations

import html
import logging
from typing import Any, Dict, List, Mapping

from domain.members.ffme_category import category_label
from exports.competitors_excel import payment_label

logger = logging.getLogger("alj")


def generate_competitors_html(comp: Mapping[str, Any], participants: List[Dict[str, Any]] | None = None) -> str:
    """Génère le code HTML prêt pour conversion PDF / impression navigateur."""
    nom_comp = html.escape(str(comp.get("nom") or "Compétition"))
    date_comp = html.escape(str(comp.get("date_competition") or ""))
    date_fin = html.escape(str(comp.get("date_fin") or date_comp))
    lieu = html.escape(str(comp.get("lieu") or ""))
    disc = html.escape(str(comp.get("type") or ""))

    date_str = f"Date : {date_comp}" if not date_fin or date_fin == date_comp else f"Dates : {date_comp} au {date_fin}"
    meta_parts = [date_str]
    if lieu:
        meta_parts.append(f"Lieu : {lieu}")
    if disc:
        meta_parts.append(f"Discipline : {disc}")
    meta_line = " · ".join(meta_parts)

    parts = participants if participants is not None else (comp.get("participants") or [])

    rows_html = []
    for i, p in enumerate(parts):
        bg = "#F8FAFC" if i % 2 == 1 else "#FFFFFF"
        nom = html.escape(str(p.get("nom") or "").strip().upper())
        prenom = html.escape(str(p.get("prenom") or "").strip().title())
        cat = html.escape(category_label(p.get("categorie"), p.get("sex")))
        surclass = "Oui" if p.get("surclassement") else "Non"
        discipline_val = html.escape(str(p.get("discipline") or disc or "").strip())
        statut = "Sélectionné" if p.get("selectionne") else "Non invité"
        paiement = html.escape(payment_label(p))
        dob = html.escape(str(p.get("date_naissance") or p.get("birth_date") or "").strip())
        licence = html.escape(str(p.get("num_licence") or p.get("licence_ffme") or "").strip())
        email = html.escape(str(p.get("email") or "").strip())
        phone = html.escape(str(p.get("phone") or p.get("telephone") or "").strip())

        rows_html.append(f"""
        <tr style="background-color: {bg};">
            <td style="font-weight: bold;">{nom}</td>
            <td>{prenom}</td>
            <td style="text-align: center;">{cat}</td>
            <td style="text-align: center;">{surclass}</td>
            <td style="text-align: center;">{discipline_val}</td>
            <td style="text-align: center;">{statut}</td>
            <td style="text-align: center;">{paiement}</td>
            <td style="text-align: center;">{dob}</td>
            <td style="text-align: center;">{licence}</td>
            <td>{email}</td>
            <td>{phone}</td>
        </tr>
        """)

    table_body = "\n".join(rows_html)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <title>Liste des compétiteurs — {nom_comp}</title>
    <style>
        @page {{
            size: A4 landscape;
            margin: 1cm;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: #1E293B;
            margin: 0;
            padding: 0;
            font-size: 11px;
        }}
        .header {{
            margin-bottom: 15px;
            border-bottom: 2px solid #1E3A8A;
            padding-bottom: 8px;
        }}
        h1 {{
            color: #1E3A8A;
            margin: 0 0 4px 0;
            font-size: 18px;
        }}
        .meta {{
            color: #475569;
            font-size: 12px;
            font-style: italic;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th {{
            background-color: #1E3A8A;
            color: #FFFFFF;
            font-weight: bold;
            padding: 6px 8px;
            text-align: left;
            border: 1px solid #CBD5E1;
            font-size: 10.5px;
            text-transform: uppercase;
        }}
        td {{
            padding: 5px 8px;
            border: 1px solid #CBD5E1;
        }}
        .print-btn {{
            position: fixed;
            top: 10px;
            right: 10px;
            background: #1E3A8A;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
        }}
        @media print {{
            .print-btn {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">🖨️ Imprimer / Enregistrer en PDF</button>
    <div class="header">
        <h1>🧗 ALJ Escalade — {nom_comp}</h1>
        <div class="meta">{meta_line} · Total : {len(parts)} compétiteur(s)</div>
    </div>
    <table>
        <thead>
            <tr>
                <th>Nom</th>
                <th>Prénom</th>
                <th style="text-align: center;">Catégorie</th>
                <th style="text-align: center;">Surclassement</th>
                <th style="text-align: center;">Discipline</th>
                <th style="text-align: center;">Statut</th>
                <th style="text-align: center;">Paiement</th>
                <th style="text-align: center;">Date naissance</th>
                <th style="text-align: center;">Licence</th>
                <th>Email</th>
                <th>Téléphone</th>
            </tr>
        </thead>
        <tbody>
            {table_body}
        </tbody>
    </table>
</body>
</html>"""


def export_competitors_pdf(comp: Mapping[str, Any], participants: List[Dict[str, Any]] | None = None) -> bytes:
    """Génère le PDF des compétiteurs via WeasyPrint si disponible, ou retourne le HTML encodé."""
    html_content = generate_competitors_html(comp, participants)
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        # Repli si WeasyPrint (Pango) non configuré sur l'environnement : la page HTML, imprimable depuis le navigateur
        logger.warning("WeasyPrint indisponible : liste des compétiteurs servie en HTML")
        return html_content.encode("utf-8")
    return HTML(string=html_content).write_pdf()
