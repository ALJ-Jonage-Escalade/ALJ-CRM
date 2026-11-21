"""Pivot table of the members (Outils page of the Vue app, vue-pivottable), from the SQLite cache."""

from __future__ import annotations

from typing import Any, Dict, List, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.reports import resolve_report_season, season_read
from api.reports.schemas import PivotRecord, PivotRecords
from api.responses import error_responses
from domain.members.age_rules import age_at, get_season_start_date, parse_birth_date
from domain.members.sex import parse_sex
from domain.members.view import fmt_first_name, fmt_last_name
from domain.utils import clean_city_name
from infrastructure.sqlite.members import MemberRepository
from services.reports.member_stats import age_band, iso_date, status_label

router = APIRouter()

def pivot_record(row: Dict[str, Any], season: str) -> PivotRecord:  # Any: a row of the SQLite view
    """A row of the members view as a row of the table. season: the season read, for the age of rows without one."""
    season_name = str(row.get("season_name") or "").strip()
    birth_date = parse_birth_date(row.get("birth_date") or row.get("birth_date_raw") or row.get("champ_Date de naissance de l'adhérent"))
    # Age at the start of the row's own season (every season: each row at its season)
    age = age_at(birth_date, get_season_start_date(season_name or season))
    order_date = iso_date(row.get("order_date"))
    return PivotRecord(
        last_name=fmt_last_name(row.get("last_name")),
        first_name=fmt_first_name(row.get("first_name")),
        sex=parse_sex(row.get("sex")),
        age=age,
        age_band=age_band(age),
        city=clean_city_name(row.get("city") or "Inconnue"),
        group=str(row.get("tarif_name") or "").strip() or "Aucun",
        status=status_label(row.get("status")),
        season=season_name or "Inconnue",
        membership_type="Déjà Membre" if (row.get("already_member") or 0) > 0 else "Nouvelle Inscription",
        order_date=order_date or "Inconnue",
        order_month=order_date[:7] or "Inconnue",
    )


def pivot_records(season: str) -> List[PivotRecord]:
    """Every member of the season (cancelled ones included: the table filters them out by default)."""
    return [pivot_record(row, season) for row in MemberRepository.list_flat_member_rows(season_read(season))]


@router.get("/api/reports/pivot-records", response_model=PivotRecords, responses=error_responses(400, 500))
def get_pivot_records(season: str = "active") -> Union[PivotRecords, JSONResponse]:
    """Members of a season for the pivot table of the Outils page ("Toutes les saisons": every season)."""
    target_season = resolve_report_season(season)
    return PivotRecords(season=target_season, records=pivot_records(target_season))
