"""domain.members.sex: the FFME sex parsed from external input."""

from __future__ import annotations

import pytest

from domain.members.sex import Sex, parse_sex


@pytest.mark.parametrize("raw", ["F", "f", " Femme ", "FÉMININ", "feminine", "Dame", "dames", "fille", "Female"])
def test_parse_sex_female_spellings(raw: str) -> None:
    assert parse_sex(raw) is Sex.FEMALE


@pytest.mark.parametrize("raw", ["H", "m", "Homme", "masculin", "Garçon", "Monsieur", "MESSIEURS", "Male"])
def test_parse_sex_male_spellings(raw: str) -> None:
    assert parse_sex(raw) is Sex.MALE


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_parse_sex_empty_is_none(raw: str | None) -> None:
    assert parse_sex(raw) is None


@pytest.mark.parametrize("raw", ["X", "Autre", "non binaire", "Inconnu", "Fe", 1])
def test_parse_sex_unknown_is_none(raw: object) -> None:
    assert parse_sex(raw) is None


@pytest.mark.parametrize("sex", list(Sex))
def test_parse_sex_idempotent(sex: Sex) -> None:
    assert parse_sex(sex) is sex
    assert parse_sex(sex.value) is sex


def test_sex_values_are_ffme_codes() -> None:
    assert [s.value for s in Sex] == ["F", "H"]
