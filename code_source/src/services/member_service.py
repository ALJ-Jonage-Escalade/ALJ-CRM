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
        """Contacts of the participants of the competitions that are not archived, the only
        member data a coach's phone keeps offline (plan phase 5). Taken from the active season,
        else from the participant's latest season (not registered again yet)."""
        ids = {p.get("adherent_id")
               for c in CompetitionService.list_competitions() if c.get("statut") != STATUT_CLOSE
               for p in c.get("participants") or []} - {None}
        if not ids:
            return []
        seasons = SeasonService.list_seasons()
        order = [seasons["active"]] + [s for s in seasons["seasons"] if s != seasons["active"]]
        rank = {s: i for i, s in enumerate(order)}
        rows = sorted(SqliteRepository.list_member_rows_of_users(ids), key=lambda r: rank.get(r["season_name"], len(rank)))
        planning = SqliteRepository.load_planning_data(log_debug=False)
        return member_view.competitor_contacts(rows, planning, seasons["active"])
