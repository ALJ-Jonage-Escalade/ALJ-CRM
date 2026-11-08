"""Pivot table of the members (Outils page of the Vue app, vue-pivottable), from the SQLite cache."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.reports import resolve_report_season, season_read
from api.reports.schemas import PivotRecord, PivotRecords
from api.responses import error_responses
from domain.members.age_rules import age_at, get_season_start_date, parse_birth_date
from domain.members.sex import parse_sex
from domain.members.view import fmt_first_name, fmt_last_name, is_cancelled
from domain.utils import clean_city_name
from infrastructure.sqlite.members import MemberRepository

router = APIRouter()

# HelloAsso and manual statuses merged into the three labels of the table
_VALIDATED = ("processed", "validated", "validé", "enregistré", "registered", "terminé", "termine", "traité", "traite")
_REFUSED = ("refused", "refusé", "refuse")

# (upper bound excluded, label), in order; the labels sort in this order too
_AGE_BANDS = ((10, "0 à 9 ans (< 10 ans)"), (18, "10 à 17 ans"), (25, "18 à 24 ans"), (30, "25 à 29 ans"),
              (40, "30 à 39 ans"), (50, "40 à 49 ans"), (65, "50 à 64 ans"))


def status_label(status: Any) -> str:  # Any: a cell of the SQLite view
    """Validé, Annulé, Refusé, or the status as written (title case)."""
    raw = str(status if status is not None else "Validé").strip()
    lowered = raw.lower()
    if lowered in _VALIDATED:
        return "Validé"
    if is_cancelled(lowered):
        return "Annulé"
    if lowered in _REFUSED:
        return "Refusé"
    return raw.title()


def age_band(age: Optional[int]) -> str:
    """Age band of the table, « Inconnue » without an age."""
    if age is None:
        return "Inconnue"
    for upper, label in _AGE_BANDS:
        if age < upper:
            return label
    return "65 ans et plus"


def iso_date(value: Any) -> str:  # Any: a cell of the SQLite view
    """Order date as YYYY-MM-DD (chronological sort and filters in the table), "" when unreadable."""
    raw = str(value or "").strip()
    try:
        return datetime.datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


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
    return [pivot_record(row, season) for row in MemberRepository.load_direct_data(season_read(season))]


@router.get("/api/reports/pivot-records", response_model=PivotRecords, responses=error_responses(400, 500))
def get_pivot_records(season: str = "active") -> Union[PivotRecords, JSONResponse]:
    """Members of a season for the pivot table of the Outils page ("Toutes les saisons": every season)."""
    target_season = resolve_report_season(season)
    return PivotRecords(season=target_season, records=pivot_records(target_season))
