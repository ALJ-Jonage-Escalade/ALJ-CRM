"""Member list of the web pages (SQLite cache of the crm_* collections, one season at a time).

The fields the browser used to compute (age, slot group, category, normalized status…)
come from domain.members.view. Knows nothing about HTTP: failures are raised as
domain.errors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from domain.competitions.models import STATUT_CLOSE
from domain.constants import resolve_season
from domain.errors import InvalidRequest, NotFound
from domain.members import view as member_view
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.planning import PlanningRepository
from services.competitions.competitions import CompetitionService
from services.documents import Doc
from services.members.seasons import SeasonService


class MemberService:

    @staticmethod
    def list_members(season: Optional[str] = None) -> Doc:
        """{season, members, creneaux} for `season` (the active season when not given)."""
        seasons = SeasonService.list_seasons()
        name = resolve_season(season) if (season or "").strip() else seasons["active"]
        if name not in seasons["seasons"]:
            raise NotFound(f"Saison inconnue : {name}.")
        planning = PlanningRepository.load_planning_data()
        rows = MemberRepository.list_member_rows(name)
        return {
            "season": name,
            "members": member_view.build_members(rows, planning, name),
            "creneaux": member_view.slot_groups(planning),
        }

    @staticmethod
    def find_member(season: Optional[str], purchase_id: int) -> Doc:
        """One member of `season` (the active season when not given), by purchase, as list_members lists it."""
        listed = MemberService.list_members(season)
        found = next((m for m in listed["members"] if m.get("purchase_id") == purchase_id), None)
        if found is None:
            raise NotFound(f"Adhérent introuvable dans la saison {listed['season']}.")
        return found

    @staticmethod
    def list_competitors() -> List[Doc]:
        """Contacts of the participants of the competitions that are not archived, the only
        member data a coach's phone keeps offline. Taken from the active season,
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
        planning = PlanningRepository.load_planning_data()
        return member_view.competitor_contacts(rows, planning, seasons["active"])

    @staticmethod
    def update_member(fields: Dict[str, Any], user_id: Optional[int] = None, purchase_id: Optional[int] = None,
                      order_ref: Optional[str] = None) -> None:  # Any: the MemberFields sent, by name
        """Writes the fields sent on the member (badges, licence, contacts, address) and on their purchase (tariff,
        amount, status, comment), found by user_id, purchase_id or order_ref."""
        if not user_id and not purchase_id and not order_ref:
            raise InvalidRequest("Identifiant d'adhérent manquant (user_id, purchase_id ou order_ref).")
        if not fields:
            raise InvalidRequest("Aucune modification à enregistrer.")
        MemberRepository.update_member_fields(user_id=user_id, fields=fields, purchase_id=purchase_id, order_ref=order_ref or None)

    @staticmethod
    def add_member(fields: Dict[str, Any], season: Optional[str] = None) -> tuple[str, str]:  # Any: as above
        """Adds a member by hand to `season` (the active one when not given). Returns (order reference, season)."""
        if not fields.get("last_name") or not fields.get("first_name"):
            raise InvalidRequest("Le nom et le prénom de l'adhérent sont obligatoires.")
        if not fields.get("birth_date"):
            raise InvalidRequest("La date de naissance est obligatoire.")
        if not fields.get("tarif_name"):
            raise InvalidRequest("Le groupe (tarif) est obligatoire.")
        target_season = resolve_season(season)
        return MemberRepository.add_manual_member(fields, season_name=target_season), target_season
