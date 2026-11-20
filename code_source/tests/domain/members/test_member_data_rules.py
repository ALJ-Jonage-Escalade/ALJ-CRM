"""Checks of a member's data at the HelloAsso import (domain/members/member_data_rules.py, issue #135). Fake data only."""

from __future__ import annotations

import datetime
from dataclasses import replace

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

    assert checked.values.birth_date == iso
    assert _birth_date_issues(raw) == []


@pytest.mark.parametrize("raw", ["11/08/13", "11-08-2013", "2013/08/11", "31/02/2013", "onze août", "08/11/2013 ou 11/08"])
def test_an_unreadable_birth_date_blocks(raw: str) -> None:
    checked = check_member_data(MemberValues(birth_date=raw), season_start=SEASON_START)

    assert checked.values.birth_date == ""
    assert _birth_date_issues(raw) == [("unreadable", True)]


def test_a_missing_birth_date_blocks() -> None:
    assert _birth_date_issues("  ") == [("missing", True)]


def _phone(raw: str, field: str = "phone") -> tuple[str, list[str]]:
    checked = check_member_data(replace(MemberValues(), **{field: raw}), season_start=SEASON_START)
    return getattr(checked.values, field), [issue.code for issue in checked.issues if issue.field == field]


@pytest.mark.parametrize(("raw", "stored"), [
    ("0612345678", "06 12 34 56 78"), ("06.12.34.56.78", "06 12 34 56 78"), ("06 12 34 56 78", "06 12 34 56 78"),
    ("+33612345678", "06 12 34 56 78"), ("+33 6 12 34 56 78", "06 12 34 56 78"), ("0033 6 12 34 56 78", "06 12 34 56 78"),
    ("+33 (0)6 12 34 56 78", "06 12 34 56 78"), ("04 78 12 34 56", "04 78 12 34 56"),
    # Foreign numbers: international format, recognisable as foreign
    ("+41 79 123 45 67", "+41 79 123 45 67"), ("0044 7911 123456", "+44 7911 123456"),
])
def test_a_valid_phone_is_stored_in_one_format_without_warning(raw: str, stored: str) -> None:
    assert _phone(raw) == (stored, [])


@pytest.mark.parametrize("raw", ["061234567", "06123456789", "06 12 AB 56 78", "molly@terrier.example", "12"])
def test_a_phone_that_cannot_be_valid_is_a_warning_and_kept_as_typed(raw: str) -> None:
    assert _phone(raw) == (raw, ["invalid"])


def test_a_missing_member_phone_is_a_warning() -> None:
    assert _phone(" ") == ("", ["missing"])


@pytest.mark.parametrize("field", ["emergency_phone_1", "emergency_phone_2"])
def test_the_emergency_phones_follow_the_same_rule_but_may_be_empty(field: str) -> None:
    assert _phone("+33612345678", field) == ("06 12 34 56 78", [])
    assert _phone("061234567", field) == ("061234567", ["invalid"])
    assert _phone("", field) == ("", [])


def test_only_the_birth_date_blocks() -> None:
    checked = check_member_data(MemberValues(birth_date="11/08/2013", phone="12", emergency_phone_1="12"), season_start=SEASON_START)

    assert checked.issues and not any(issue.blocking for issue in checked.issues)


# The domain check, faked: "gmial.com" cannot receive mail, "lent.example" does not answer
DOMAINS = {"gmial.com": False, "lent.example": None}


def _email(raw: str, field: str = "email") -> tuple[str, list[str]]:
    checked = check_member_data(replace(MemberValues(), **{field: raw}), season_start=SEASON_START,
                                domain_accepts_mail=lambda domain: DOMAINS.get(domain, True))
    return getattr(checked.values, field), [issue.code for issue in checked.issues if issue.field == field]


@pytest.mark.parametrize(("raw", "stored"), [
    ("molly@terrier.example", "molly@terrier.example"), (" Molly.Weasley@Terrier.Example ", "Molly.Weasley@terrier.example"),
    ("molly@lent.example", "molly@lent.example"),  # the domain check failed: no warning
])
def test_a_valid_email_is_stored_normalised_without_warning(raw: str, stored: str) -> None:
    assert _email(raw) == (stored, [])


@pytest.mark.parametrize("raw", ["molly weasley@terrier.example", "molly.terrier.example", "06 12 34 56 78", "molly@terrier"])
def test_an_email_with_invalid_syntax_is_a_warning_and_kept_as_typed(raw: str) -> None:
    assert _email(raw) == (raw, ["invalid"])


def test_an_email_whose_domain_cannot_receive_mail_is_a_warning() -> None:
    assert _email("molly@gmial.com") == ("molly@gmial.com", ["no_mail_domain"])


def test_a_missing_primary_email_is_a_warning_but_the_second_one_may_be_empty() -> None:
    assert _email("") == ("", ["missing"])
    assert _email("", "email_2") == ("", [])
    assert _email("molly@gmial.com", "email_2") == ("molly@gmial.com", ["no_mail_domain"])


def test_without_domain_check_no_domain_is_flagged() -> None:
    checked = check_member_data(MemberValues(email="molly@gmial.com"), season_start=SEASON_START)

    assert [issue.code for issue in checked.issues if issue.field == "email"] == []


def _value(field: str, raw: str) -> tuple[str, list[str]]:
    checked = check_member_data(replace(MemberValues(), **{field: raw}), season_start=SEASON_START)
    return getattr(checked.values, field), [issue.code for issue in checked.issues if issue.field == field]


@pytest.mark.parametrize(("field", "raw", "stored"), [
    ("country", "france", "France"), ("country", "FR", "France"), ("country", "Allemagne", "Allemagne"),
    ("country", " royaume uni ", "Royaume-Uni"),
    ("nationality", "FRANCAISE", "Française"), ("nationality", "Français", "Française"), ("nationality", "FR", "Française"),
    ("nationality", "Allemagne", "Allemande"),
])
def test_a_recognised_country_or_nationality_is_stored_in_its_canonical_spelling(field: str, raw: str, stored: str) -> None:
    assert _value(field, raw) == (stored, [])


@pytest.mark.parametrize("field", ["country", "nationality"])
def test_an_unknown_or_missing_country_or_nationality_is_a_warning(field: str) -> None:
    assert _value(field, "Bretagne") == ("Bretagne", ["unknown"])
    assert _value(field, "") == ("", ["missing"])


@pytest.mark.parametrize(("raw", "stored", "issues"), [
    ("123456", "123456", []), (" 12 34 56 ", "123456", []), ("1234567", "1234567", []),
    ("", "", []), ("non", "", []), ("en cours", "", []),  # no licence: never a warning
    ("12345", "12345", ["invalid"]), ("12345678", "12345678", ["invalid"]),
])
def test_an_ffme_licence_must_have_six_or_seven_digits(raw: str, stored: str, issues: list[str]) -> None:
    assert _value("licence", raw) == (stored, issues)
