"""Rows of the member charts (Outils › Statistiques of the Vue app), from the SQLite cache."""

from __future__ import annotations

from fastapi import APIRouter

from api.reports.schemas import MemberStatsRecord, MemberStatsRecords
from api.responses import error_responses
from services.reports.member_stats import member_stats_rows

router = APIRouter()


@router.get("/api/reports/member-stats", response_model=MemberStatsRecords, responses=error_responses(500))
def get_member_stats() -> MemberStatsRecords:
    """Every purchase of every season, without names: the page filters the season and counts people itself."""
    return MemberStatsRecords(records=[MemberStatsRecord(**row) for row in member_stats_rows()])
