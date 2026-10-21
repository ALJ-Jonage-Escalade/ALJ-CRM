"""Pivot table of the members of a season (PivotTable.js), from the SQLite cache."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from domain.utils import json_for_script

router = APIRouter()


@router.get("/pivot", response_class=HTMLResponse)
def get_pivot_table(season: str = "2026-2027"):
    """Renvoie la page du Tableau Croisé Dynamique interactif via PivotTable.js."""
    try:
        from infrastructure.sqlite.members import MemberRepository
        from domain.constants import get_active_season
        from domain.members.age_rules import parse_birth_date, age_at, get_season_start_date
        from domain.members.models import normalize_gender
        from domain.utils import clean_city_name
        
        target_season = (season or "").strip()
        if not target_season or target_season.lower() in ("default", "active"):
            target_season = get_active_season()

        raw_data = MemberRepository.load_direct_data(target_season)
        ref_date = get_season_start_date(target_season)
        
        # Préparer un tableau de données plat et épuré pour le TCD
        pivot_records = []
        for row in raw_data:
            # 1. Normaliser et fusionner les statuts HelloAsso (Processed, Validated, Terminé, Traité -> Validé)
            status_raw = str(row.get("status", "Validé")).strip()
            status_lower = status_raw.lower()
            if status_lower in ("processed", "validated", "validé", "enregistré", "registered", "terminé", "termine", "traité", "traite"):
                status_clean = "Validé"
            elif status_lower in ("canceled", "cancelled", "annulé", "annule"):
                status_clean = "Annulé"
            elif status_lower in ("refused", "refusé", "refuse"):
                status_clean = "Refusé"
            else:
                status_clean = status_raw.title()
                
            # 2. Normaliser les noms de villes pour fusionner "Saint-Maurice..." et "Saint Maurice..."
            city_raw = row.get("city") or "Inconnue"
            city_clean = clean_city_name(city_raw)
            
            # 3. Type d'adhésion (Nouveau vs Déjà membre)
            already_member = row.get("already_member", 0)
            inscription_type = "Déjà Membre" if already_member > 0 else "Nouvelle Inscription"
            
            # 4. Saison
            season_name = row.get("season_name", "Inconnue")
            
            # 5. Date d'inscription (normalisée en ISO AAAA-MM-JJ pour un tri
            #    et un filtrage chronologiques dans le TCD ; format source variable)
            date_iso = ""
            date_raw = str(row.get("order_date") or "").strip()
            if date_raw:
                try:
                    import datetime as _datetime
                    date_iso = _datetime.datetime.strptime(date_raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                except ValueError:
                    date_iso = ""
            month_iso = date_iso[:7] if date_iso else ""

            # 6. Âge de l'adhérent (calculé au début de la saison de référence)
            b_date = parse_birth_date(row.get("birth_date") or row.get("birth_date_raw") or row.get("champ_Date de naissance de l'adhérent"))
            computed_age = age_at(b_date, ref_date)
            age_val = computed_age if computed_age is not None else "Inconnu"

            # 7. Tranche d'Âge (regroupement par décennies & mineurs, ordonné pour le tri TCD)
            if computed_age is None:
                tranche_age = "Inconnue"
            elif computed_age < 10:
                tranche_age = "0 à 9 ans (< 10 ans)"
            elif computed_age < 18:
                tranche_age = "10 à 17 ans"
            elif computed_age < 25:
                tranche_age = "18 à 24 ans"
            elif computed_age < 30:
                tranche_age = "25 à 29 ans"
            elif computed_age < 40:
                tranche_age = "30 à 39 ans"
            elif computed_age < 50:
                tranche_age = "40 à 49 ans"
            elif computed_age < 65:
                tranche_age = "50 à 64 ans"
            else:
                tranche_age = "65 ans et plus"
            
            pivot_records.append({
                "Nom": (row.get("last_name") or "").strip().upper(),
                "Prénom": (row.get("first_name") or "").strip().title(),
                "Sexe": normalize_gender(row.get("gender")) or "Inconnu",
                "Âge": age_val,
                "Tranche d'Âge": tranche_age,
                "Ville": city_clean,
                "Groupe / Tarif": str(row.get("tarif_name") or "").strip() or "Aucun",
                "Statut": status_clean,
                "Saison": season_name,
                "Type d'Adhésion": inscription_type,
                "Date d'Inscription": date_iso or "Inconnue",
                "Mois d'Inscription": month_iso or "Inconnue",
            })
            
        pivot_data_json = json_for_script(pivot_records)
    except Exception as ex:
        print(f"⚠️ Erreur lors de la préparation des données TCD : {ex}")
        pivot_data_json = "[]"

    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>ALJ Escalade - Tableau Croisé Dynamique</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <!-- jQuery et jQuery UI (Requis par PivotTable.js) -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jqueryui/1.12.1/jquery-ui.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/jqueryui/1.12.1/jquery-ui.min.css">
    
    <!-- PivotTable.js (CSS & JS) -->
    <link rel="stylesheet" type="text/css" href="https://cdnjs.cloudflare.com/ajax/libs/pivottable/2.23.0/pivot.min.css">
    <script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/pivottable/2.23.0/pivot.min.js"></script>
    
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 25px;
            background-color: #F8FAFC;
            color: #1E293B;
        }
        .header {
            background-color: #1E3A8A;
            color: #FFFFFF;
            padding: 15px 25px;
            border-radius: 8px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
        }
        .header h1 {
            margin: 0;
            font-size: 20px;
            font-weight: bold;
        }
        .header p {
            margin: 5px 0 0 0;
            font-size: 13px;
            color: #BFDBFE;
        }
        .container {
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
            overflow: auto;
        }
        /* Style personnalisé pour les tables PivotTable.js */
        table.pvtTable {
            font-family: inherit;
            border-collapse: collapse;
            font-size: 13px;
        }
        table.pvtTable tr th, table.pvtTable tr th.pvtAxisLabel, table.pvtTable tr th.pvtTotalLabel {
            background-color: #F1F5F9;
            border: 1px solid #CBD5E1;
            color: #334155;
            font-weight: bold;
            padding: 6px 10px;
        }
        table.pvtTable tr td {
            color: #475569;
            border: 1px solid #CBD5E1;
            padding: 6px 10px;
            background-color: #FFFFFF;
        }
        .pvtValActive {
            background-color: #3B82F6 !important;
            color: #FFFFFF !important;
        }
        .pvtRowLabel, .pvtColLabel {
            font-weight: 500;
        }
        select.pvtAttrDropdown, select.pvtAggregator {
            font-family: inherit;
            padding: 4px 8px;
            border: 1px solid #CBD5E1;
            border-radius: 4px;
            background-color: #FFFFFF;
            color: #334155;
            font-size: 12px;
            margin: 3px;
        }
        .pvtVals {
            display: inline-block;
        }
    </style>
</head>
<body>

    <div class="header">
        <h1>📊 Tableau Croisé Dynamique — ALJ Escalade</h1>
        <p>Glissez et déposez les étiquettes ci-dessous pour filtrer et croiser à volonté les adhérents (par Groupe / Tarif, Sexe, Statut, Âge, Tranche d'Âge, Ville, etc.)</p>
    </div>

    <div class="container">
        <div id="output"></div>
    </div>

    <script type="text/javascript">
        $(function(){
            const pivotData = {PIVOT_DATA_JSON};
            
            $("#output").pivotUI(pivotData, {
                rows: ["Groupe / Tarif"],
                cols: ["Statut", "Sexe"],
                exclusions: {
                    "Groupe / Tarif": ["Liste d'attente cours"],
                    "Statut": ["Annulé"]
                },
                aggregatorName: "Count",
                rendererName: "Table"
            });
        });
    </script>
</body>
</html>
""".replace("{PIVOT_DATA_JSON}", pivot_data_json)
    return HTMLResponse(content=html_content)
