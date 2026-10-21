"""Member list of the web pages (SQLite cache of the crm_* collections, one season at a time).

The fields the browser used to compute (age, slot group, category, normalized status…)
come from domain.members.view. Knows nothing about HTTP: failures are raised as
services.errors.
"""

from __future__ import annotations

from typing import List, Optional

from domain.members import view as member_view
from domain.competitions.models import STATUT_CLOSE
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.planning import PlanningRepository
from services.competitions.competitions import CompetitionService
from services.documents import Doc
from services.errors import NotFound
from services.members.seasons import SeasonService


class MemberService:

    @staticmethod
    def list_members(season: Optional[str] = None) -> Doc:
        """{season, members, creneaux} for `season` (the active season when not given)."""
        seasons = SeasonService.list_seasons()
        name = (season or "").strip() or seasons["active"]
        if name not in seasons["seasons"]:
            raise NotFound(f"Saison inconnue : {name}.")
        planning = PlanningRepository.load_planning_data(log_debug=False)
        rows = MemberRepository.list_member_rows(name)
        return {
            "season": name,
            "members": member_view.build_members(rows, planning, name),
            "creneaux": member_view.creneaux(planning),
        }

    @staticmethod
    def list_competitors() -> List[Doc]:
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
        rows = sorted(MemberRepository.list_member_rows_of_users(ids), key=lambda r: rank.get(r["season_name"], len(rank)))
        planning = PlanningRepository.load_planning_data(log_debug=False)
        return member_view.competitor_contacts(rows, planning, seasons["active"])
