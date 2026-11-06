"""Emergency contacts: cleaning, what counts as the same contact (plans/emergency-contacts.md, D3, D5)."""
from __future__ import annotations

import pytest

from domain.members.emergency_contacts import EmergencyContact, clean_contacts, missing_contacts, same_contact


def test_clean_contacts_strips_values_and_keeps_order() -> None:
    assert clean_contacts([{"name": "  Zoé ", "phone": " 0601020304 "}, {"name": "Anna", "phone": ""}]) == [
        EmergencyContact("Zoé", "0601020304"),
        EmergencyContact("Anna", ""),
    ]


@pytest.mark.parametrize("blank", [{"name": "", "phone": ""}, {"name": "  ", "phone": " "}, {"name": None, "phone": None}, {}])
def test_clean_contacts_drops_blank_rows(blank: dict[str, str | None]) -> None:
    assert clean_contacts([blank, {"name": "Anna"}, blank]) == [EmergencyContact("Anna", "")]


def test_clean_contacts_keeps_a_row_with_only_a_phone() -> None:
    assert clean_contacts([{"phone": "0601020304"}]) == [EmergencyContact("", "0601020304")]


@pytest.mark.parametrize("spelling", ["0601020304", "06 01 02 03 04", "06.01.02.03.04", "+33601020304", "+33 6 01 02 03 04", "0033601020304"])
def test_same_phone_in_any_spelling_is_the_same_contact(spelling: str) -> None:
    assert same_contact(EmergencyContact("Marie", "0601020304"), EmergencyContact("Autre nom", spelling))


def test_different_phones_under_one_name_are_two_contacts() -> None:
    assert not same_contact(EmergencyContact("Marie", "0601020304"), EmergencyContact("Marie", "0699999999"))


@pytest.mark.parametrize("name", ["MARTIN Élodie", "martin elodie", "  Martin  Elodie "])
def test_without_a_phone_the_name_decides(name: str) -> None:
    assert same_contact(EmergencyContact("Martin Elodie", ""), EmergencyContact(name, ""))
    assert same_contact(EmergencyContact("Martin Elodie", "0601020304"), EmergencyContact(name, ""))


def test_a_new_phone_under_a_known_name_is_not_the_same_contact() -> None:
    # Otherwise the number would be lost: rows already there are never changed (D2)
    assert not same_contact(EmergencyContact("Marie", ""), EmergencyContact("Marie", "0601020304"))


def test_a_phone_without_digits_counts_as_no_phone() -> None:
    assert same_contact(EmergencyContact("Marie", "0601020304"), EmergencyContact("Marie", "inconnu"))


def test_missing_contacts_keeps_only_what_is_new_in_order() -> None:
    existing = [EmergencyContact("Marie", "0601020304")]
    incoming = [{"name": "Paul", "phone": "0611111111"}, {"name": "Marie D.", "phone": "+33601020304"}, {"name": "Anna", "phone": ""}]
    assert missing_contacts(existing, incoming) == [EmergencyContact("Paul", "0611111111"), EmergencyContact("Anna", "")]


def test_missing_contacts_removes_duplicates_within_incoming() -> None:
    incoming = [{"name": "Marie", "phone": "0601020304"}, {"name": "Marie", "phone": "06 01 02 03 04"}, {"name": "", "phone": ""}]
    assert missing_contacts([], incoming) == [EmergencyContact("Marie", "0601020304")]

