"""Member list of the web pages (SQLite cache of the crm_* collections, one season at a time).

The fields the browser used to compute (age, slot group, category, normalized status…)
come from domain.member_view. Knows nothing about HTTP: failures are raised as
services.errors.
"""

from typing import Any, Dict, List, Optional

from domain import member_view
from domain.competition_models import STATUT_CLOSE
from infrastructure.sqlite_repository import SqliteRepository
from services.competition_service import CompetitionService
from services.errors import NotFound
from services.season_service import SeasonService


class MemberService:

    @staticmethod
    def list_members(season: Optional[str] = None) -> Dict[str, Any]:
        """{season, members, creneaux} for `season` (the active season when not given)."""
        seasons = SeasonService.list_seasons()
        season = (season or "").strip() or seasons["active"]
        if season not in seasons["seasons"]:
            raise NotFound(f"Saison inconnue : {season}.")
        planning = SqliteRepository.load_planning_data(log_debug=False)
        rows = SqliteRepository.list_member_rows(season)
        return {
            "season": season,
            "members": member_view.build_members(rows, planning, season),
            "creneaux": member_view.creneaux(planning),
        }

    @staticmethod
    def list_competitors() -> List[Dict[str, Any]]:
        """Contacts of the participants of the competitions that are not archived (active
        season), the only member data a coach's phone keeps offline (plan phase 5)."""
        ids = {p.get("adherent_id")
               for c in CompetitionService.list_competitions() if c.get("statut") != STATUT_CLOSE
               for p in c.get("participants") or []}
        if not ids:
            return []
        season = SeasonService.list_seasons()["active"]
        planning = SqliteRepository.load_planning_data(log_debug=False)
        members = member_view.build_members(SqliteRepository.list_member_rows(season), planning, season)
        return member_view.competitor_contacts(members, ids)
