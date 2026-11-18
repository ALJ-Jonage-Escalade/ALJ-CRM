"""Who appears on the attendance sheets, shared by the presence screen counts and the generated sheets.

Rules:
- A cancelled or refunded registration (`is_cancelled`) never appears.
- One person is listed once, whatever their number of registrations: identity = first name,
  last name and birth date (`member_identity_key`).
- An autonomous-slot member whose birth date is unreadable counts as an adult: those slots are adult tariffs.
- A member from another group with a parental authorisation (autonomous or family) is an authorised minor
  unless their birth date shows they are 18 or older: the authorisation only exists for minors, so an
  unreadable birth date keeps them on the autonomous sheet.
- The members of the course tariffs in AUTONOMOUS_EXTRA_TARIFS are listed on the autonomous sheet as well
  (their course keeps its own sheet).
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from domain.members.age_rules import ADULT_AGE, age_at, parse_birth_date
from domain.members.view import is_cancelled

# A row of the flat member view (MemberRepository.list_flat_member_rows): values are text, numbers or None.
MemberRow = Mapping[str, Any]

IdentityKey = tuple[str, str, str]

# HelloAsso tariffs of courses whose members also climb on autonomous slots: listed on the autonomous sheet too.
AUTONOMOUS_EXTRA_TARIFS = ("Perfectionnement U19 Adulte",)


def member_birth_date(member: MemberRow) -> datetime.date | None:
    """Birth date of a member row: the v2 key, else the HelloAsso custom field; None when unreadable."""
    return parse_birth_date(member.get("birth_date") or member.get("champ_Date de naissance de l'adhérent"))


def member_identity_key(member: MemberRow) -> IdentityKey:
    """(first name, last name, ISO birth date) in lower case, used to list a person once."""
    birth_date = member_birth_date(member)
    return (
        str(member.get("first_name") or "").strip().lower(),
        str(member.get("last_name") or "").strip().lower(),
        birth_date.isoformat() if birth_date else "",
    )


def has_parental_authorization(member: MemberRow) -> bool:
    """True when a parent allowed the member to climb on autonomous slots or with their family."""
    return any(str(member.get(field) or "").strip() == "Oui" for field in ("parental_auth_autonomous", "parental_auth_family"))


def is_adult(member: MemberRow, today: datetime.date) -> bool | None:
    """18 or older today; None when the birth date is unreadable."""
    age = age_at(member_birth_date(member), today)
    return None if age is None else age >= ADULT_AGE


def is_authorized_minor(member: MemberRow, today: datetime.date) -> bool:
    """Parental authorisation and not known to be an adult (see the module rules)."""
    return has_parental_authorization(member) and is_adult(member, today) is not True


def active_members(members: Iterable[MemberRow]) -> list[MemberRow]:
    """The members to list: registrations not cancelled nor refunded, one per person (first one kept)."""
    seen: set[IdentityKey] = set()
    kept = []
    for member in members:
        if is_cancelled(member.get("status")):
            continue
        key = member_identity_key(member)
        if key not in seen:
            seen.add(key)
            kept.append(member)
    return kept


def members_with_tarifs(members: Iterable[MemberRow], tarifs: Iterable[str]) -> list[MemberRow]:
    """Active members (see active_members) registered on one of these HelloAsso tariffs."""
    wanted = {str(tarif).strip() for tarif in tarifs}
    return active_members(member for member in members if str(member.get("tarif_name") or "").strip() in wanted)


def authorized_minors(members: Iterable[MemberRow], today: datetime.date) -> list[MemberRow]:
    """Active members of any group who may join the autonomous sheet as authorised minors."""
    return active_members(member for member in members if is_authorized_minor(member, today))


@dataclass(frozen=True)
class AutonomousCounts:
    """People on the autonomous sheet: its own members split by age, plus the authorised minors of other groups."""
    adults: int
    minors: int
    authorized_minors: int

    @property
    def total(self) -> int:
        return self.adults + self.minors + self.authorized_minors


def count_autonomous(members: Iterable[MemberRow], autonomous_tarifs: Iterable[str], today: datetime.date) -> AutonomousCounts:
    """Counts shown on the presence screen, computed with the rules the generated sheet uses
    (the AUTONOMOUS_EXTRA_TARIFS members count as the sheet's own)."""
    rows = list(members)
    own = members_with_tarifs(rows, [*autonomous_tarifs, *AUTONOMOUS_EXTRA_TARIFS])
    own_keys = {member_identity_key(member) for member in own}
    minors = sum(1 for member in own if is_adult(member, today) is False)
    added = [member for member in authorized_minors(rows, today) if member_identity_key(member) not in own_keys]
    return AutonomousCounts(adults=len(own) - minors, minors=minors, authorized_minors=len(added))
