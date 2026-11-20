"""Checks of a member's data at the HelloAsso import (domain/members/member_data_rules.py, issue #135). Fake data only."""

from __future__ import annotations

import datetime

import pytest

from domain.members.member_data_rules import MemberValues, check_member_data

SEASON_START = datetime.date(2026, 9, 1)


def _birth_date_issues(raw: str) -> list[tuple[str, bool]]:
    checked = check_member_data(MemberValues(birth_date=raw), season_start=SEASON_START)
    return [(issue.code, issue.blocking) for issue in checked.issues if issue.field == "birth_date"]


def test_a_birth_date_in_the_future_blocks() -> None:
    assert _birth_date_issues("01/01/2030") == [("future", True)]


@pytest.mark.parametrize(("raw", "expected"), [
    ("01/09/2023", []),  # 3 years old on the season start
    ("02/09/2023", [("too_young", True)]),  # the registration year typed in, or nearly
    ("01/09/2026", [("too_young", True)]),
    ("02/09/1925", []),  # 100 years old
    ("01/09/1925", [("too_old", True)]),  # 101 on the season start
    ("01/01/1026", [("too_old", True)]),
])
def test_a_birth_date_giving_an_implausible_age_on_the_season_start_blocks(raw: str, expected: list[tuple[str, bool]]) -> None:
    assert _birth_date_issues(raw) == expected


@pytest.mark.parametrize(("raw", "iso"), [
    ("11/08/2013", "2013-08-11"), (" 11/08/2013 ", "2013-08-11"),
    ("2013-08-11", "2013-08-11"), ("2013-08-11T00:00:00", "2013-08-11"),  # HelloAsso date fields
])
def test_a_readable_birth_date_is_stored_as_iso(raw: str, iso: str) -> None:
    checked = check_member_data(MemberValues(birth_date=raw), season_start=SEASON_START)

    assert (checked.values.birth_date, checked.issues) == (iso, ())


@pytest.mark.parametrize("raw", ["11/08/13", "11-08-2013", "2013/08/11", "31/02/2013", "onze août", "08/11/2013 ou 11/08"])
def test_an_unreadable_birth_date_blocks(raw: str) -> None:
    checked = check_member_data(MemberValues(birth_date=raw), season_start=SEASON_START)

    assert checked.values.birth_date == ""
    assert [(issue.code, issue.blocking) for issue in checked.issues] == [("unreadable", True)]


def test_a_missing_birth_date_blocks() -> None:
    assert _birth_date_issues("  ") == [("missing", True)]
