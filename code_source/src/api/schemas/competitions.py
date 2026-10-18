"""Bodies of the competition routes (api.competitions)."""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import Field, field_validator

from api.schemas.base import RequestBody
from domain.competition_models import STATUT_EN_PREPARATION, STATUTS_COMPETITION

_ISO_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})?$")


def _check_statut(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in STATUTS_COMPETITION:
        raise ValueError(f"statut must be one of {', '.join(STATUTS_COMPETITION)}")
    return value


def _distinct(value: Optional[List[int]]) -> Optional[List[int]]:
    """Coach ids in the order given, duplicates dropped (no length limit, plan C2)."""
    return None if value is None else list(dict.fromkeys(value))


def _check_date(value: Optional[str]) -> Optional[str]:
    if value is not None and not _ISO_DATE.match(value):
        raise ValueError("date must be YYYY-MM-DD or empty")
    return value


class CompetitionCreate(RequestBody):
    nom: str = Field(min_length=1)
    id_ffme: str = ""
    date_competition: str = ""
    date_fin: str = ""
    prix: float = Field(0.0, ge=0)
    statut: str = STATUT_EN_PREPARATION
    coach_ids: List[int] = Field(default_factory=list)
    helloasso_ref: str = ""
    url_resultats: str = ""  # MyCompet results page, also found by the fetch-results route
    whatsapp_link: str = ""
    # Pass-through fields of the bureau page, stored without validation (plan appendix B)
    lieu: Optional[str] = None
    type: Optional[str] = None

    _statut = field_validator("statut")(_check_statut)
    _dates = field_validator("date_competition", "date_fin")(_check_date)
    _coaches = field_validator("coach_ids")(_distinct)


class CompetitionUpdate(RequestBody):
    """Partial update: only the fields sent are changed."""
    nom: Optional[str] = Field(None, min_length=1)
    id_ffme: Optional[str] = None
    date_competition: Optional[str] = None
    date_fin: Optional[str] = None
    prix: Optional[float] = Field(None, ge=0)
    statut: Optional[str] = None
    coach_ids: Optional[List[int]] = None
    helloasso_ref: Optional[str] = None
    url_resultats: Optional[str] = None
    whatsapp_link: Optional[str] = None
    lieu: Optional[str] = None
    type: Optional[str] = None

    _statut = field_validator("statut")(_check_statut)
    _dates = field_validator("date_competition", "date_fin")(_check_date)
    _coaches = field_validator("coach_ids")(_distinct)
