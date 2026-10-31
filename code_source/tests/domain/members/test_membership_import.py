"""Membership import planner: every HelloAsso registration lands in exactly one bucket, with a reason (fake data only)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import (
    Bucket,
    Decision,
    ImportPlan,
    StaleDecisions,
    WriteAction,
    apply_decisions,
    plan_membership_import,
)

SEASON = "2026-2027"
CAMPAIGN = "adhesion-escalade-2026-2027-amicale-laique-escalade-2"


def _record(item_id: int = 9001, **overrides: object) -> MembershipRecord:
    record = MembershipRecord(
        item_id=item_id, order_ref=f"ORD-{item_id}", order_date="2026-09-01T10:00:00", status="Processed",
        tarif_name="Loisir collège", amount=150.0, last_name="Weasley", first_name="Ginny",
        payer_last_name="Weasley", payer_first_name="Molly", payer_email="molly@terrier.example",
        birth_date="2013-08-11", birth_date_raw="11/08/2013", licence="",
    )
    return replace(record, **overrides)  # type: ignore[arg-type]  # overrides of the dataclass fields


def test_an_unknown_person_is_new() -> None:
    plan = plan_membership_import([_record()], season=SEASON, campaign_slug=CAMPAIGN)

    [entry] = plan.entries
    assert (entry.item_id, entry.bucket) == (9001, Bucket.NEW)
    assert entry.reason
    assert plan.blocked_reason is None


def test_a_campaign_of_another_season_blocks_every_registration() -> None:
    plan = plan_membership_import([_record(1), _record(2)], season=SEASON, campaign_slug="adhesion-escalade-2025-2026")

    assert plan.blocked_reason is not None
    assert [(entry.bucket, entry.reason) for entry in plan.entries] == [(Bucket.BLOCKED, plan.blocked_reason)] * 2


@pytest.mark.parametrize(
    "overrides",
    [{"last_name": ""}, {"first_name": "  "}, {"order_ref": ""}, {"birth_date": "", "birth_date_raw": "onze août"}],
)
def test_a_registration_without_name_order_or_birth_date_is_blocked(overrides: dict[str, str]) -> None:
    [entry] = plan_membership_import([_record(**overrides)], season=SEASON, campaign_slug=CAMPAIGN).entries

    assert entry.bucket == Bucket.BLOCKED
    assert entry.reason


def test_counts_cover_every_bucket() -> None:
    plan = plan_membership_import([_record(1), _record(2, last_name="")], season=SEASON, campaign_slug=CAMPAIGN)

    assert plan.counts() == {"already_imported": 0, "new": 1, "renewal": 0, "updated": 0, "to_review": 0, "blocked": 1}


# ---------------------------------------------------------------------------
# Decisions applier: the admin's decisions, keyed by HelloAsso item id, become the writes
# ---------------------------------------------------------------------------
def _new_plan() -> ImportPlan:
    return plan_membership_import([_record(1), _record(2, first_name="Ron"), _record(3, last_name="")], season=SEASON,
                                  campaign_slug=CAMPAIGN)


def test_checked_new_rows_are_created_and_unchecked_ones_skipped() -> None:
    writes = apply_decisions(_new_plan(), {1: Decision(Bucket.NEW, "import"), 2: Decision(Bucket.NEW, "skip")})

    assert [(write.item_id, write.action) for write in writes] == [(1, WriteAction.CREATE)]


def test_a_row_without_decision_is_skipped() -> None:
    """A registration that appeared on HelloAsso after the preview was never seen by the admin."""
    assert apply_decisions(_new_plan(), {1: Decision(Bucket.NEW, "import")}) == apply_decisions(
        _new_plan(), {1: Decision(Bucket.NEW, "import"), 2: Decision(Bucket.NEW, "skip")})


@pytest.mark.parametrize(
    "decisions",
    [
        {99: Decision(Bucket.NEW, "import")},  # unknown item
        {1: Decision(Bucket.RENEWAL, "import")},  # the row changed bucket since the preview
        {3: Decision(Bucket.BLOCKED, "import")},  # a blocked row cannot be imported
        {1: Decision(Bucket.NEW, "link:7")},  # not a choice of a new row
    ],
)
def test_stale_or_invalid_decisions_are_rejected(decisions: dict[int, Decision]) -> None:
    with pytest.raises(StaleDecisions):
        apply_decisions(_new_plan(), decisions)


def test_nothing_is_written_from_a_blocked_campaign() -> None:
    plan = plan_membership_import([_record(1)], season=SEASON, campaign_slug="adhesion-2025-2026")

    with pytest.raises(StaleDecisions):
        apply_decisions(plan, {1: Decision(Bucket.NEW, "import")})
