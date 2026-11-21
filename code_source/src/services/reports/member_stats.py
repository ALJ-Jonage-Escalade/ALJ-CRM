"""Rows behind the member charts of Outils › Statistiques: one per purchase of every season, without names
(plans/stats-charts.md). The browser counts people, groups and seasons from them."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, TypedDict

from domain.members.age_rules import age_at, get_season_start_date, parse_birth_date
from domain.members.sex import Sex, parse_sex
from domain.members.view import is_cancelled
from domain.utils import clean_city_name
from infrastructure.sqlite.members import MemberRepository

UNKNOWN = "Inconnue"

# HelloAsso and manual statuses merged into the three labels of the statistics
_VALIDATED = ("processed", "validated", "validé", "enregistré", "registered", "terminé", "termine", "traité", "traite")
_REFUSED = ("refused", "refusé", "refuse")

# (upper bound excluded, label), in order; the labels sort in this order too
_AGE_BANDS = ((10, "0 à 9 ans (< 10 ans)"), (18, "10 à 17 ans"), (25, "18 à 24 ans"), (30, "25 à 29 ans"),
              (40, "30 à 39 ans"), (50, "40 à 49 ans"), (65, "50 à 64 ans"))


class MemberStatsRow(TypedDict):
    """A purchase as a row of the statistics. age: at the start of the row's season, None without a birth date;
    returning: the member already belonged to the club; order_month: YYYY-MM or « Inconnue »."""
    user_id: int
    sex: Optional[Sex]
    age: Optional[int]
    age_band: str
    city: str
    group: str
    status: str
    season: str
    returning: bool
    order_month: str


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
    """Age band of the statistics, « Inconnue » without an age."""
    if age is None:
        return UNKNOWN
    for upper, label in _AGE_BANDS:
        if age < upper:
            return label
    return "65 ans et plus"


def iso_date(value: Any) -> str:  # Any: a cell of the SQLite view
    """Order date as YYYY-MM-DD, "" when unreadable."""
    raw = str(value or "").strip()
    try:
        return datetime.datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def member_stats_row(row: Dict[str, Any]) -> MemberStatsRow:  # Any: a row of the SQLite view
    """A row of the members view as a row of the statistics."""
    season = str(row.get("season_name") or "").strip()
    birth_date = parse_birth_date(row.get("birth_date") or row.get("birth_date_raw") or row.get("champ_Date de naissance de l'adhérent"))
    age = age_at(birth_date, get_season_start_date(season)) if season else None
    return MemberStatsRow(
        user_id=int(row["user_id"]),
        sex=parse_sex(row.get("sex")),
        age=age,
        age_band=age_band(age),
        city=clean_city_name(row.get("city") or UNKNOWN),
        group=str(row.get("tarif_name") or "").strip() or "Aucun",
        status=status_label(row.get("status")),
        season=season or UNKNOWN,
        returning=(row.get("already_member") or 0) > 0,
        order_month=iso_date(row.get("order_date"))[:7] or UNKNOWN,
    )


def member_stats_rows() -> List[MemberStatsRow]:
    """Every purchase of every season (cancelled and refused ones included: the page counts them apart)."""
    return [member_stats_row(row) for row in MemberRepository.list_flat_member_rows(None)]
