"""FFME competition category of a member for a season (U11 … VETERAN_2).

The category depends on the birth **year** only and on the season: the age reached during the calendar year in
which the season ends (season "2026-2027" → age in 2027). It changes on 1 September, with the season. Below 9 there
is no category (no competition at that age). A FFME change of the bands is a change of `_BANDS`.
"""

from __future__ import annotations

import datetime
from enum import StrEnum


class Category(StrEnum):
    U11 = "U11"
    U13 = "U13"
    U15 = "U15"
    U17 = "U17"
    U19 = "U19"
    SENIOR = "SENIOR"
    VETERAN_1 = "VETERAN_1"
    VETERAN_2 = "VETERAN_2"


# (lowest age of the band, category), youngest first: a member is in the last band whose lowest age they reached
_BANDS: tuple[tuple[int, Category], ...] = (
    (9, Category.U11),
    (11, Category.U13),
    (13, Category.U15),
    (15, Category.U17),
    (17, Category.U19),
    (19, Category.SENIOR),
    (40, Category.VETERAN_1),
    (50, Category.VETERAN_2),
)


def category_for(birth_date: datetime.date | None, season: str) -> Category | None:
    """The category of someone born on `birth_date` for `season` ("2026-2027"); None below 9 or without a birth date.
    ValueError for a season that is not "YYYY-YYYY"."""
    if birth_date is None:
        return None
    age = int(season.split("-", 1)[0]) + 1 - birth_date.year
    found: Category | None = None
    for lowest_age, category in _BANDS:
        if age >= lowest_age:
            found = category
    return found


# The French labels of the server's documents (exports, e-mails); the app has its own (frontend/src/lib/category.ts)
_LABELS: dict[Category, str] = {**{c: c.value for c in (Category.U11, Category.U13, Category.U15, Category.U17, Category.U19)},
                                Category.SENIOR: "Sénior", Category.VETERAN_1: "Vétéran 1", Category.VETERAN_2: "Vétéran 2"}


def category_label(code: object, sex: object = None) -> str:
    """The label with the sex initial ("U13 F", "Sénior H"), alone without a sex; "" without a category or for an
    unknown code."""
    try:
        label = _LABELS[Category(str(code or ""))]
    except ValueError:
        return ""
    return f"{label} {sex}" if sex else label
