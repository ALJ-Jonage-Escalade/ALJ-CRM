"""domain.members.ffme_category: the FFME category of a member for a season."""

from __future__ import annotations

import datetime

import pytest

from domain.members.ffme_category import Category, category_for, category_label


@pytest.mark.parametrize(("birth_year", "expected"), [
    (2018, Category.U11), (2017, Category.U11),
    (2016, Category.U13), (2015, Category.U13),
    (2014, Category.U15), (2013, Category.U15),
    (2012, Category.U17), (2011, Category.U17),
    (2010, Category.U19), (2009, Category.U19),
    (2008, Category.SENIOR), (1988, Category.SENIOR),
    (1987, Category.VETERAN_1), (1978, Category.VETERAN_1),
    (1977, Category.VETERAN_2), (1940, Category.VETERAN_2),
])
def test_category_for_season_2026_2027(birth_year: int, expected: Category) -> None:
    assert category_for(datetime.date(birth_year, 6, 15), "2026-2027") is expected


@pytest.mark.parametrize(("birth_year", "expected"), [
    (2019, Category.U11), (2017, Category.U13), (2009, Category.SENIOR), (1988, Category.VETERAN_1), (1978, Category.VETERAN_2),
])
def test_category_for_next_season_moves_everyone_up_a_year(birth_year: int, expected: Category) -> None:
    assert category_for(datetime.date(birth_year, 1, 1), "2027-2028") is expected


@pytest.mark.parametrize("birth_date", [datetime.date(2019, 1, 1), datetime.date(2024, 12, 31), None])
def test_category_for_under_9_or_without_birth_date_is_none(birth_date: datetime.date | None) -> None:
    assert category_for(birth_date, "2026-2027") is None


@pytest.mark.parametrize(("code", "sex", "expected"), [
    ("U13", "F", "U13 F"), ("SENIOR", "H", "Sénior H"), ("VETERAN_1", None, "Vétéran 1"), ("", "F", ""), ("U99", "F", ""), (None, "H", ""),
])
def test_category_label_with_the_sex(code: str | None, sex: str | None, expected: str) -> None:
    assert category_label(code, sex) == expected
