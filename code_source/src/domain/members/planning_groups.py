"""
Groupes de créneaux du planning et fiches de présence.

Un groupe de créneau du planning peut regrouper plusieurs créneaux horaires et plusieurs
tarifs HelloAsso (PlanningRepository.load_creneaux_groups()). La case « Séance autonome »
d'un créneau décide de la fiche autonome : un groupe coché de type Autonome forme la fiche,
un groupe coché d'un autre type (ex. Perfectionnement U19 Adulte) y ajoute ses inscrits et
garde sa propre fiche de cours. Ce module reste pur.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from domain.utils import normalize_string

# A group of PlanningRepository.load_creneaux_groups(): groupe, tarifs, slots, seance_autonome, type_autonome
CreneauGroup = Mapping[str, object]


def is_autonomous_type(slot_type: object) -> bool:
    """Vrai pour le type « autonome » d'un créneau (accents / majuscules ignorés)."""
    return normalize_string(str(slot_type or "")) == "autonome"


def forms_autonomous_sheet(creneau: CreneauGroup) -> bool:
    """Groupe dont la fiche autonome est faite (titre, QR codes, horaires) : coché et de type Autonome.
    Il n'a pas de fiche de cours."""
    return bool(creneau.get("seance_autonome")) and bool(creneau.get("type_autonome"))


def joins_autonomous_sheet(creneau: CreneauGroup) -> bool:
    """Groupe de cours coché « Séance autonome » : ses inscrits sont ajoutés à la fiche autonome."""
    return bool(creneau.get("seance_autonome")) and not creneau.get("type_autonome")


def autonomous_sheet_extra_tarifs(creneaux: Iterable[CreneauGroup]) -> list[str]:
    """Tarifs HelloAsso des groupes de cours ajoutés à la fiche autonome (joins_autonomous_sheet)."""
    return [str(t) for c in creneaux if joins_autonomous_sheet(c) for t in _tarifs(c)]


def _tarifs(creneau: CreneauGroup) -> list[str]:
    tarifs = creneau.get("tarifs")
    return [str(t) for t in tarifs] if isinstance(tarifs, list) else []


def group_for_tarif(tarif_name: str, planning_data) -> str:
    """Nom du groupe de créneau associé à un tarif HelloAsso ("" si non rapproché).

    Comparaison insensible aux accents/majuscules/espaces superflus ; le planning
    est la liste des créneaux (PlanningRepository.load_planning_data) portant chacun
    un champ `groupe` et un payload `helloasso_tarifs`.
    """
    target = normalize_string(tarif_name)
    if not target:
        return ""
    for item in planning_data or []:
        for t in item.get("helloasso_tarifs") or []:
            if normalize_string(t) == target:
                return str(item.get("groupe") or "").strip()
    return ""
