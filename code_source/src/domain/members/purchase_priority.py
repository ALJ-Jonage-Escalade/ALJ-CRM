"""Priority of a person's registrations in a season: the one that counts when a person has several (a refunded,
cancelled or waiting-list registration never hides a paid one). Shared by the member writers (schema_v2), the FFME
export, the competitions' member list and the HelloAsso membership import planner."""

from __future__ import annotations

from typing import Any

# Table de priorité des statuts — CENTRALISÉE (phase 3)
# "Terminé" = licence FFME confirmée : état le plus avancé du workflow, il ne doit
# jamais être rétrogradé par une nouvelle synchro HelloAsso ("Validated"/"Validé").
STATUS_PRIORITY = {
    "processed": 10,
    "traité": 10,
    "traite": 10,
    "validated": 9,
    "validé": 8,
    "valide": 8,
    "terminé": 10,
    "termine": 10,
    "en cours": 5,
    "canceled": 1,
    "annulé": 1,
    "annule": 1,
    "refunded": 1,
    "refunding": 1,
}


def status_score(status: Any) -> int:  # Any: any stored or HelloAsso status
    return STATUS_PRIORITY.get(str(status or "").strip().lower(), 0)


def purchase_priority_score(status: Any, tarif_name: Any, amount: Any) -> int:  # Any: values as stored
    """Score de priorité d'une inscription : statut + pénalité liste d'attente / montant nul."""
    base = status_score(status)
    tarif_lower = str(tarif_name or "").strip().lower()
    try:
        amt_val = float(amount) if amount else 0.0
    except (ValueError, TypeError):
        amt_val = 0.0
    if "attente" in tarif_lower or amt_val == 0.0:
        base -= 20
    return base
