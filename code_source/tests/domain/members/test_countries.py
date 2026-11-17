"""Country and nationality codes of the FFME export (domain/members/countries.py, issue #117)."""

from __future__ import annotations

import pytest

from domain.members.countries import COUNTRIES, _key, _spellings, country_names, nationality_names, parse_country

# Every distinct value stored in production when the table was written (November 2026), and what it gives
PRODUCTION_VALUES = {
    "France": "FR", "FRANCE": "FR", "france": "FR",
    "Française": "FR", "Français": "FR", "Francaise": "FR", "française": "FR", "FRANCAISE": "FR", "francaise": "FR",
    "FRANCAIS": "FR", "français": "FR", "francais": "FR", "Francais": "FR", "Francaises": "FR", "FRA": "FR", "Fr": "FR",
    # Typos: never guessed, the office corrects the record
    "Fràce": None, "F": None, "Frncaise": None, "Francaisz": None, "Sueddois": None,
}


@pytest.mark.parametrize(("raw", "code"), PRODUCTION_VALUES.items())
def test_parse_country_production_values(raw: str, code: str | None) -> None:
    country = parse_country(raw)
    assert (country.code if country else None) == code


@pytest.mark.parametrize(("raw", "code"), [
    # Wrong before issue #117: first two letters of the name, or « FR » found inside the text
    ("Irlande", "IE"), ("Allemagne", "DE"), ("Algérie", "DZ"), ("Royaume-Uni", "GB"), ("Pays-Bas", "NL"),
    ("États-Unis", "US"), ("Suisse", "CH"), ("Portugal", "PT"), ("Afrique du Sud", "ZA"), ("Sud-africaine", "ZA"),
    ("Belge", "BE"), ("Suédoise", "SE"), ("suedois", "SE"),
    # Hyphens, spaces, apostrophes, codes
    (" royaume uni ", "GB"), ("Côte d’Ivoire", "CI"), ("ie", "IE"), ("DEU", "DE"), ("Néerlandais", "NL"), ("Hollande", "NL"),
])
def test_parse_country_spellings(raw: str, code: str) -> None:
    country = parse_country(raw)
    assert country is not None and country.code == code


@pytest.mark.parametrize("raw", ["", "   ", None, "Afrique", "Bretagne", "ÉT", "PO", "Française et belge"])
def test_parse_country_not_recognised(raw: str | None) -> None:
    assert parse_country(raw) is None


def test_no_spelling_designates_two_countries() -> None:
    seen: dict[str, str] = {}
    for country in COUNTRIES:
        for spelling in _spellings(country):
            assert seen.setdefault(_key(spelling), country.code) == country.code, spelling


def test_codes_are_unique_iso_shaped() -> None:
    assert len({c.code for c in COUNTRIES}) == len(COUNTRIES)
    assert all(len(c.code) == 2 and len(c.alpha3) == 3 and c.code.isupper() for c in COUNTRIES)


def test_form_choices_are_recognised_and_unique() -> None:
    for names in (country_names(), nationality_names()):
        assert len(set(names)) == len(names)
        assert all(parse_country(name) is not None for name in names)
    assert country_names()[0] == "France" and nationality_names()[0] == "Française"
