"""Sex of a member: the FFME administrative sex (HelloAsso "Sexe", FFME export, competition categories).

Parsed once at the input boundary (HelloAsso, Excel, legacy data) with `parse_sex`; the rest of the code
handles a `Sex` or `None` (not given). Gender identity, if the club ever needs it, is a separate field.
"""

from __future__ import annotations

from enum import StrEnum

from domain.utils import normalize_string


class Sex(StrEnum):
    """FFME codes (column "sexe" of the FFME CSV)."""

    FEMALE = "F"
    MALE = "H"


_SPELLINGS: dict[str, Sex] = {
    **dict.fromkeys(("f", "femme", "femmes", "feminin", "feminine", "dame", "dames", "fille", "female"), Sex.FEMALE),
    **dict.fromkeys(("h", "m", "homme", "hommes", "masculin", "garcon", "monsieur", "messieurs", "male"), Sex.MALE),
}


def parse_sex(raw: object) -> Sex | None:
    """Sex read from an external value, lenient on spelling, case and accents ("Féminin", " homme ", "F").

    `None` when the value is empty or not understood: the caller decides whether to log it
    (this function stays pure). Idempotent: `parse_sex(Sex.FEMALE) == Sex.FEMALE`.
    """
    return _SPELLINGS.get(normalize_string(raw))
