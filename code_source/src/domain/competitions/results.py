"""Competition results rules: when a competition is over, whether its results are in, and matching the scraped
MyCompet rankings to the club's participants."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Mapping, Optional, TypedDict

from domain.utils import normalize_name


class ClubAthlete(TypedDict):
    """A club member's result, for the summary e-mail and the report."""
    nom: str
    prenom: str
    num_licence: str
    categorie: str
    classement: str
    total_categorie: int
    resultat_ffme: str
    performance: str


def end_date(competition: Mapping[str, Any]) -> Optional[datetime.date]:  # Any: Firestore competition document
    """Last day of a competition (`date_fin`, else `date_competition`), None when unknown."""
    target = str(competition.get("date_fin") or "").strip() or str(competition.get("date_competition") or "").strip()
    try:
        return datetime.date.fromisoformat(target[:10]) if target else None
    except ValueError:
        return None


def is_competition_past(competition: Mapping[str, Any], today: Optional[datetime.date] = None) -> bool:  # Any: as above
    """True once the competition's last day has come."""
    ended = end_date(competition)
    return ended is not None and ended <= (today or datetime.date.today())


def has_results(competition: Mapping[str, Any]) -> bool:  # Any: as above
    """True when results were synced and at least one participant has a ranking."""
    rows = competition.get("participants") or []
    has_rankings = any(str(row.get("classement") or "").strip() or str(row.get("resultat_ffme") or "").strip() for row in rows)
    return bool(competition.get("resultats_synced_at") and has_rankings)


def _rank_sort_key(athlete: ClubAthlete) -> int:
    try:
        return int(athlete["classement"])
    except ValueError:
        return 9999


def apply_rankings(participants: List[Dict[str, Any]], scraped: List[Dict[str, Any]],
                   synced_at: str) -> List[ClubAthlete]:  # Any: Firestore participant rows and scraper rows
    """Sets the ranking fields of the participants found in the scraped results (licence first, then name), in place.
    Only those fields are changed. Returns the matched athletes, best ranked first."""
    by_licence: Dict[str, Dict[str, Any]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for row in scraped:
        licence = str(row.get("licence") or "").strip()
        if licence:
            by_licence[licence] = row
        full_name = normalize_name(f"{row.get('nom') or ''} {row.get('prenom') or ''}")
        if full_name:
            by_name[full_name] = row

    athletes: List[ClubAthlete] = []
    for participant in participants:
        licence = str(participant.get("num_licence") or "").strip()
        full_name = normalize_name(f"{participant.get('nom') or ''} {participant.get('prenom') or ''}")
        match = (by_licence.get(licence) if licence else None) or (by_name.get(full_name) if full_name else None)
        if not match:
            continue
        rank = str(match.get("classement") or "").strip()
        total = int(match.get("total_categorie") or 0)
        suffix = f" / {total}" if total > 0 else "e"
        participant["classement"] = rank
        participant["total_categorie"] = total
        participant["resultat_ffme"] = f"{rank}{suffix}" if rank else ""
        participant["categorie_ffme"] = match.get("categorie") or ""
        participant["performance_ffme"] = match.get("performance") or ""
        participant["resultat_synced_at"] = synced_at
        athletes.append(ClubAthlete(
            nom=str(participant.get("nom") or match.get("nom") or ""),
            prenom=str(participant.get("prenom") or match.get("prenom") or ""),
            num_licence=licence or str(match.get("licence") or ""),
            categorie=str(match.get("categorie") or participant.get("categorie") or ""),
            classement=rank,
            total_categorie=total,
            resultat_ffme=participant["resultat_ffme"],
            performance=str(match.get("performance") or ""),
        ))
    athletes.sort(key=_rank_sort_key)
    return athletes
