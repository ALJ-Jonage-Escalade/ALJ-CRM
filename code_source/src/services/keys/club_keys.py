"""Club keys: the rules of adding, assigning, returning and archiving a key (plans/club-keys.md).

Knows nothing about HTTP: refusals are raised as domain.errors.
"""

from __future__ import annotations

from typing import List, Literal, Optional, TypedDict, Union

from domain.errors import Conflict, InvalidRequest, NotFound
from infrastructure.sqlite.keys import AssignmentRow, EventRow, HolderRow, KeyRepository, KeyRow
from services.members.seasons import SeasonService


class Holder(TypedDict):
    user_id: int
    last_name: str
    first_name: str
    given_on: str
    comment: str
    member_this_season: bool  # False: to chase up, the holder has no membership of the active season
    season: str  # season of the holder's record: the active one, else their last one


class Key(TypedDict):
    id: int
    code: str
    status: str
    holder: Optional[Holder]


class AssignmentEntry(AssignmentRow):
    kind: Literal["assignment"]


class EventEntry(EventRow):
    kind: Literal["event"]


HistoryEntry = Union[AssignmentEntry, EventEntry]


def _active_season() -> str:
    return SeasonService.list_seasons()["active"]


def _active_members() -> set[int]:
    return KeyRepository.members_of_season(_active_season())


def _holder(row: HolderRow, active_season: str, members: set[int]) -> Holder:
    member = row["user_id"] in members
    return Holder(user_id=row["user_id"], last_name=row["last_name"], first_name=row["first_name"], given_on=row["given_on"],
                  comment=row["comment"], member_this_season=member, season=active_season if member else row["last_season"])


def _key(key_id: int) -> KeyRow:
    key = KeyRepository.get_key(key_id)
    if key is None:
        raise NotFound("Clé introuvable.")
    return key


def _day(iso: str) -> str:
    """2027-01-05 -> 05/01/2027"""
    year, month, day = iso[:10].split("-")
    return f"{day}/{month}/{year}"


def _assignment(assignment_id: int) -> AssignmentRow:
    assignment = KeyRepository.get_assignment(assignment_id)
    if assignment is None:
        raise NotFound("Attribution introuvable.")
    return assignment


class KeyService:

    @staticmethod
    def list_keys() -> List[Key]:
        season = _active_season()
        members = KeyRepository.members_of_season(season)
        return [Key(id=k["id"], code=k["code"], status=k["status"], holder=_holder(k["holder"], season, members) if k["holder"] else None)
                for k in KeyRepository.list_keys()]

    @staticmethod
    def add_key(code: str) -> KeyRow:
        return KeyRepository.add_key(code)

    @staticmethod
    def assign(key_id: int, user_id: int, given_on: str, comment: str, by: str) -> None:
        key = _key(key_id)
        if key["status"] != "available":
            raise Conflict(f"La clé « {key['code']} » n'est pas disponible.", "key_not_available")
        held = KeyRepository.key_held_by(user_id)
        if held is not None:
            raise Conflict(f"Cet adhérent détient déjà la clé « {held} ».", "member_has_key")
        if user_id not in _active_members():
            raise Conflict("Seul un adhérent de la saison active peut recevoir une clé.", "not_a_member")
        KeyRepository.assign(key_id, user_id, given_on, comment, by)

    @staticmethod
    def give_back(key_id: int, returned_on: str, comment: str) -> None:
        key = _key(key_id)
        if key["holder"] is None:
            raise Conflict(f"Personne ne détient la clé « {key['code']} ».", "key_not_held")
        if returned_on < key["holder"]["given_on"]:
            raise InvalidRequest("La date de retour précède la date de remise.")
        KeyRepository.close_assignment(key_id, returned_on, comment)

    @staticmethod
    def history(key_id: int) -> List[HistoryEntry]:
        """Assignments (by handover date) and events (by date), oldest first."""
        _key(key_id)
        entries: List[tuple[str, HistoryEntry]] = [
            (a["given_on"], AssignmentEntry(**a, kind="assignment")) for a in KeyRepository.assignments(key_id)]
        entries += [(e["date"], EventEntry(**e, kind="event")) for e in KeyRepository.events(key_id)]
        return [entry for _, entry in sorted(entries, key=lambda pair: pair[0])]

    @staticmethod
    def rename(key_id: int, code: str, by: str) -> None:
        key = _key(key_id)
        if code != key["code"]:
            KeyRepository.rename(key_id, code, f"{key['code']} → {code}", by)

    @staticmethod
    def correct_assignment(assignment_id: int, given_on: str, returned_on: Optional[str], comment: str, return_comment: str) -> None:
        """Fixes the dates and comments of an assignment; whether the key is still held does not change."""
        assignment = _assignment(assignment_id)
        if (assignment["returned_on"] is None) != (returned_on is None):
            raise InvalidRequest("La date de retour ne se corrige que sur une clé rendue : enregistrez plutôt son retour.")
        if returned_on is not None and returned_on < given_on:
            raise InvalidRequest("La date de retour précède la date de remise.")
        KeyRepository.update_assignment(assignment_id, given_on, returned_on, comment, return_comment)

    @staticmethod
    def delete_assignment(assignment_id: int, by: str) -> None:
        """Only the key's latest assignment (entered by mistake): older ones are its history."""
        assignment = _assignment(assignment_id)
        latest = KeyRepository.assignments(assignment["key_id"])[-1]
        if latest["id"] != assignment_id:
            raise Conflict("Seule la dernière attribution d'une clé peut être supprimée.", "not_latest")
        who = f"{assignment['last_name']} {assignment['first_name']}".strip()
        KeyRepository.delete_assignment(assignment, f"{who}, remise le {_day(assignment['given_on'])}", by)
