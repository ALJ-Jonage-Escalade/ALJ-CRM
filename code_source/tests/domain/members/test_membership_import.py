"""Membership import planner: every HelloAsso registration lands in exactly one bucket, with a reason (fake data only)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import Bucket, plan_membership_import

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
