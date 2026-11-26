"""Who appears on the attendance sheets (shared by the presence screen and the generated sheets)."""
from __future__ import annotations

import datetime
from typing import Any

import pytest

from domain.activities.presence_rules import (
    AutonomousCounts,
    authorized_minors,
    count_autonomous,
    is_authorized_minor,
    member_birth_date,
    member_identity_key,
    members_with_tarifs,
)

TODAY = datetime.date(2026, 11, 8)


def _member(first: str, last: str, birth: str | None, tarif: str = "Loisir", status: str = "Validated", **extra: Any) -> dict[str, Any]:
    return {"first_name": first, "last_name": last, "birth_date": birth, "tarif_name": tarif, "status": status, **extra}


@pytest.mark.parametrize(("row", "expected"), [
    ({"birth_date": "2012-03-04"}, datetime.date(2012, 3, 4)),
    ({"birth_date": "2012-03-04T00:00:00"}, datetime.date(2012, 3, 4)),
    ({"champ_Date de naissance de l'adhérent": "04/03/2012"}, datetime.date(2012, 3, 4)),
    ({"birth_date": "inconnue"}, None),
    ({}, None),
])
def test_member_birth_date_reads_both_keys(row: dict[str, Any], expected: datetime.date | None) -> None:
    assert member_birth_date(row) == expected


def test_member_identity_key_ignores_case_and_spaces() -> None:
    assert member_identity_key(_member(" Leo ", "MARTIN", "2012-03-04")) == ("leo", "martin", "2012-03-04")
    assert member_identity_key(_member("Leo", "Martin", None)) == ("leo", "martin", "")


@pytest.mark.parametrize("status", ["Annulé", "Refunded", "Remboursé", "Canceled"])
def test_members_with_tarifs_leaves_out_cancelled_and_refunded(status: str) -> None:
    members = [_member("Leo", "Martin", "2012-03-04", status=status), _member("Lea", "Durand", "2010-01-01")]
    assert [m["first_name"] for m in members_with_tarifs(members, ["Loisir"])] == ["Lea"]


def test_members_with_tarifs_lists_a_person_once() -> None:
    members = [_member("Leo", "Martin", "2012-03-04"), _member("LEO", "martin", "2012-03-04", tarif="Loisir ")]
    assert len(members_with_tarifs(members, ["Loisir"])) == 1


@pytest.mark.parametrize(("birth", "expected"), [
    ("2012-03-04", True),    # 14
    ("2008-11-08", False),   # 18 today
    (None, True),            # unreadable: the authorisation only exists for minors
])
def test_is_authorized_minor(birth: str | None, expected: bool) -> None:
    assert is_authorized_minor(_member("Leo", "Martin", birth, parental_auth_family="Oui"), TODAY) is expected


def test_is_authorized_minor_needs_an_authorisation() -> None:
    assert not is_authorized_minor(_member("Leo", "Martin", "2012-03-04", parental_auth_family="Non"), TODAY)


def test_authorized_minors_leaves_out_cancelled_registrations() -> None:
    members = [_member("Leo", "Martin", "2012-03-04", status="Annulé", parental_auth_autonomous="Oui")]
    assert authorized_minors(members, TODAY) == []


def test_count_autonomous_matches_the_sheet_rules() -> None:
    members = [
        _member("Ana", "Adulte", "1990-01-01", tarif="Adultes autonomes"),
        _member("Bob", "Inconnu", None, tarif="Adultes autonomes"),                       # unreadable: adult
        _member("Cleo", "Jeune", "2010-01-01", tarif="Adultes autonomes"),                # minor of the slot
        _member("Cleo", "Jeune", "2010-01-01", tarif="Adultes autonomes"),                # same person twice
        _member("Dan", "Ailleurs", "2012-01-01", parental_auth_autonomous="Oui"),        # authorised minor
        _member("Eve", "Ailleurs", None, parental_auth_family="Oui"),                     # authorised, birth date unreadable
        _member("Cleo", "Jeune", "2010-01-01", parental_auth_family="Oui"),               # already on the sheet
        _member("Fay", "Annulee", "2012-01-01", status="Annulé", parental_auth_family="Oui"),
    ]
    counts = count_autonomous(members, {"Adultes autonomes"}, TODAY)
    assert counts == AutonomousCounts(adults=2, minors=1, authorized_minors=2)
    assert counts.total == 5
