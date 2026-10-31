"""Membership import planner: sorts the HelloAsso registrations of the season into buckets (pure, no I/O).

Every registration lands in exactly one bucket, with the reason shown to the admin in the preview
(plans/helloasso-membership-import.md). The import recomputes the same plan before applying the admin's decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional

from domain.members.helloasso_membership import MembershipRecord, season_guard


class Bucket(str, Enum):
    ALREADY_IMPORTED = "already_imported"
    NEW = "new"
    RENEWAL = "renewal"
    UPDATED = "updated"
    TO_REVIEW = "to_review"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PlanEntry:
    """What the import would do with one registration."""
    record: MembershipRecord
    bucket: Bucket
    reason: str

    @property
    def item_id(self) -> int:
        return self.record.item_id


@dataclass(frozen=True)
class ImportPlan:
    season: str
    campaign_slug: str
    entries: list[PlanEntry] = field(default_factory=list)
    blocked_reason: Optional[str] = None  # the whole campaign is refused (season guard)

    def counts(self) -> dict[str, int]:
        """Number of registrations per bucket, every bucket listed."""
        counts = {bucket.value: 0 for bucket in Bucket}
        for entry in self.entries:
            counts[entry.bucket.value] += 1
        return counts


def _missing_data(record: MembershipRecord) -> Optional[str]:
    """Why a registration cannot be imported as it is, None when nothing essential is missing."""
    if not record.last_name.strip() or not record.first_name.strip():
        return "Nom ou prénom de l'adhérent manquant sur HelloAsso."
    if not record.order_ref:
        return "Référence de commande HelloAsso manquante."
    if not record.birth_date:
        return "Date de naissance manquante ou illisible."
    return None


def _classify(record: MembershipRecord) -> PlanEntry:
    missing = _missing_data(record)
    if missing:
        return PlanEntry(record, Bucket.BLOCKED, missing)
    return PlanEntry(record, Bucket.NEW, "Personne inconnue du club : nouvel adhérent.")


def plan_membership_import(records: Iterable[MembershipRecord], *, season: str, campaign_slug: str) -> ImportPlan:
    """The plan of the import of these registrations into `season`."""
    records = list(records)
    blocked_reason = season_guard(campaign_slug, season)
    if blocked_reason:
        entries = [PlanEntry(record, Bucket.BLOCKED, blocked_reason) for record in records]
    else:
        entries = [_classify(record) for record in records]
    return ImportPlan(season=season, campaign_slug=campaign_slug, entries=entries, blocked_reason=blocked_reason)


# ---------------------------------------------------------------------------
# Decisions applier: the admin's choices on the preview become the writes
# ---------------------------------------------------------------------------
IMPORT = "import"  # a checked new / renewal / updated row
SKIP = "skip"  # an unchecked row; the default of every row


class StaleDecisions(ValueError):
    """The decisions do not match the plan recomputed on confirm (unknown item, bucket changed, invalid choice)."""


@dataclass(frozen=True)
class Decision:
    """The admin's choice for one row, with the bucket the preview showed it in."""
    bucket: Bucket
    choice: str


class WriteAction(str, Enum):
    CREATE = "create"  # new member, with this season's membership


@dataclass(frozen=True)
class ImportWrite:
    entry: PlanEntry
    action: WriteAction

    @property
    def item_id(self) -> int:
        return self.entry.item_id


def _write_for(entry: PlanEntry, decision: Decision) -> Optional[ImportWrite]:
    if decision.bucket != entry.bucket:
        raise StaleDecisions(f"Inscription {entry.item_id} : elle a changé sur HelloAsso depuis l'aperçu.")
    if decision.choice == SKIP:
        return None
    if entry.bucket == Bucket.NEW and decision.choice == IMPORT:
        return ImportWrite(entry, WriteAction.CREATE)
    raise StaleDecisions(f"Inscription {entry.item_id} : choix « {decision.choice} » impossible.")


def apply_decisions(plan: ImportPlan, decisions: Mapping[int, Decision]) -> list[ImportWrite]:
    """The writes of the admin's decisions, in the order of the plan. A row without decision is skipped (unchecked, or
    not shown by the preview). Raises StaleDecisions when one decision does not match the plan: nothing is written."""
    entries = {entry.item_id: entry for entry in plan.entries}
    unknown = sorted(set(decisions) - set(entries))
    if unknown:
        raise StaleDecisions(f"Inscriptions inconnues de la campagne : {', '.join(map(str, unknown))}.")
    writes = []
    for entry in plan.entries:
        decision = decisions.get(entry.item_id)
        write = _write_for(entry, decision) if decision else None
        if write:
            writes.append(write)
    return writes
