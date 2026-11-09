"""Club keys: the rules of adding, assigning, returning and archiving a key (plans/club-keys.md).

Knows nothing about HTTP: refusals are raised as domain.errors.
"""

from __future__ import annotations

from typing import List, Optional, TypedDict

from domain.errors import Conflict, InvalidRequest, NotFound
from infrastructure.sqlite.keys import HolderRow, KeyRepository, KeyRow
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
