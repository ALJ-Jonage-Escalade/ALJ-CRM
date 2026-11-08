from __future__ import annotations

import os
import re

from domain.errors import InvalidRequest

# Saison active par défaut
DEFAULT_SEASON = "2026-2027"
APP_VERSION = "2.49.0"

# Tarifs permanents disponibles hors créneau de cours (ex: licence seule)
DEFAULT_EXTRA_TARIFS = ["Licence sèche"]

def get_active_season() -> str:
    """
    Récupère la saison active configurée dans le fichier .env (ACTIVE_SEASON)
    ou retourne la saison par défaut '2026-2027'.
    """
    val = os.getenv("ACTIVE_SEASON")
    if not val or not val.strip():
        return DEFAULT_SEASON
    return val.strip()

INVALID_SEASON = "Saison invalide (format attendu : AAAA-AAAA)."
# Values of a request's season that mean "the active season"
_ACTIVE_SEASON_ALIASES = ("", "active", "default")


def resolve_season(season: str | None) -> str:
    """The season a request asks for: the active one when empty ("active" and "default" too).
    InvalidRequest when it is not a season name ('AAAA-AAAA')."""
    target = (season or "").strip()
    if target.lower() in _ACTIVE_SEASON_ALIASES:
        return get_active_season()
    if not is_valid_season(target):
        raise InvalidRequest(INVALID_SEASON)
    return target


def is_valid_season(season: str) -> bool:
    """Saison au format 'AAAA-AAAA' (ex : '2026-2027'), seul format accepté depuis une requête
    (la valeur finit dans des noms de fichiers et des en-têtes HTTP)."""
    return bool(re.fullmatch(r"\d{4}-\d{4}", season))
