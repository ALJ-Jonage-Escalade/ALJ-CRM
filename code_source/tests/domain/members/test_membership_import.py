"""Membership import planner: every HelloAsso registration lands in exactly one bucket, with a reason (fake data only)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import (
    Bucket,
    Decision,
    ImportPlan,
    KnownMember,
    KnownPurchase,
    MembersSnapshot,
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
    [{"last_name": ""}, {"first_name": "  "}, {"order_ref": ""}],
)
def test_a_registration_without_name_or_order_is_blocked(overrides: dict[str, str]) -> None:
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


# ---------------------------------------------------------------------------
# Re-runs and renewals: the planner against the members already in the base
# ---------------------------------------------------------------------------
GINNY = KnownMember(user_id=7, last_name="WEASLEY", first_name="Ginny", birth_date="2013-08-11", licence="123456")
LUNA = KnownMember(user_id=8, last_name="LOVEGOOD", first_name="Luna", birth_date="2012-02-13", licence="")


def _purchase(purchase_id: int, user_id: int, **overrides: object) -> KnownPurchase:
    purchase = KnownPurchase(purchase_id=purchase_id, user_id=user_id, order_ref="ORD-9001", season=SEASON, helloasso_item_id=None,
                             status="Processed", tarif_name="Loisir collège", amount=150.0)
    return replace(purchase, **overrides)  # type: ignore[arg-type]  # overrides of the dataclass fields


def _plan(*records: MembershipRecord, members: tuple[KnownMember, ...] = (GINNY, LUNA),
          purchases: tuple[KnownPurchase, ...] = ()) -> ImportPlan:
    snapshot = MembersSnapshot(members=list(members), purchases=list(purchases))
    return plan_membership_import(records, snapshot=snapshot, season=SEASON, campaign_slug=CAMPAIGN)


def test_a_registration_whose_item_id_is_stored_is_already_imported() -> None:
    [entry] = _plan(_record(9001), purchases=(_purchase(30, 7, helloasso_item_id=9001),)).entries

    assert (entry.bucket, entry.member_id, entry.purchase_id, entry.backfill) == (Bucket.ALREADY_IMPORTED, 7, 30, False)


def test_a_legacy_purchase_of_the_same_order_and_person_is_already_imported_and_back_filled() -> None:
    [entry] = _plan(_record(9001, last_name="Weasley"), purchases=(_purchase(30, 7),)).entries

    assert (entry.bucket, entry.member_id, entry.purchase_id, entry.backfill) == (Bucket.ALREADY_IMPORTED, 7, 30, True)


def test_a_legacy_purchase_of_the_same_order_but_another_person_does_not_match() -> None:
    [entry] = _plan(_record(9001, last_name="Lovegood", first_name="Luna", birth_date="2012-02-13"),
                    purchases=(_purchase(30, 7),)).entries

    assert (entry.bucket, entry.member_id) == (Bucket.RENEWAL, 8)


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"last_name": "Weasley", "first_name": "ginny"}, "same name and birth date"),
        ({"last_name": "WEASLEY", "licence": "123456"}, "same name, birth date and licence"),
        ({"last_name": "WEASLEY", "licence": "123456", "birth_date": "", "birth_date_raw": "?"}, "no birth date, unique licence"),
        ({"last_name": "Weasley", "licence": "999999"}, "same name and birth date, licence unknown to the club"),
    ],
)
def test_a_known_person_is_a_renewal(overrides: dict[str, str], why: str) -> None:
    [entry] = _plan(_record(9001, **overrides)).entries

    assert (entry.bucket, entry.member_id) == (Bucket.RENEWAL, 7), why


def test_a_known_licence_never_makes_a_duplicate_nor_drops_the_row() -> None:
    plan = _plan(_record(1, last_name="Weasley", licence="123456"), _record(2, last_name="Weasley", first_name="Ron", licence=""))

    assert [entry.bucket for entry in plan.entries] == [Bucket.RENEWAL, Bucket.NEW]


@pytest.mark.parametrize(
    ("registrations", "expected"),
    [
        # (status, tariff, amount) of two registrations of one person this season
        ((("Refunded", "Loisir collège", 150.0), ("Processed", "Loisir collège", 150.0)), [Bucket.BLOCKED, Bucket.NEW]),
        ((("Processed", "Liste d'attente cours", 0.0), ("Processed", "Loisir collège", 150.0)), [Bucket.BLOCKED, Bucket.NEW]),
        ((("Processed", "Loisir collège", 150.0), ("Processed", "Compétition", 200.0)), [Bucket.NEW, Bucket.NEW]),
    ],
)
def test_the_priority_score_decides_between_several_registrations_of_one_person(
        registrations: tuple[tuple[str, str, float], ...], expected: list[Bucket]) -> None:
    records = [_record(i, last_name="Granger", first_name="Hermione", order_ref=f"ORD-{i}", status=status, tarif_name=tarif, amount=amount)
               for i, (status, tarif, amount) in enumerate(registrations, start=1)]

    plan = _plan(*records)

    assert [entry.bucket for entry in plan.entries] == expected
    if Bucket.BLOCKED in expected:
        assert "prioritaire" in plan.entries[0].reason


def test_a_registration_below_the_membership_already_recorded_this_season_is_blocked() -> None:
    [entry] = _plan(_record(9001, last_name="Weasley", order_ref="ORD-2", status="Canceled"),
                    purchases=(_purchase(30, 7, order_ref="ORD-1", helloasso_item_id=8000),)).entries

    assert entry.bucket == Bucket.BLOCKED
    assert "prioritaire" in entry.reason


def test_a_checked_renewal_is_attached_to_the_known_member() -> None:
    plan = _plan(_record(1, last_name="Weasley"))

    [write] = apply_decisions(plan, {1: Decision(Bucket.RENEWAL, "import")})

    assert (write.action, write.entry.member_id) == (WriteAction.ATTACH, 7)


def test_legacy_purchases_are_back_filled_without_decision() -> None:
    plan = _plan(_record(1, last_name="Weasley"), purchases=(_purchase(30, 7, order_ref="ORD-1"),))

    [write] = apply_decisions(plan, {})

    assert (write.action, write.entry.purchase_id) == (WriteAction.BACKFILL, 30)


# ---------------------------------------------------------------------------
# "À vérifier": ambiguous identities are left to the admin, with the candidate members
# ---------------------------------------------------------------------------
GINNY_TWIN = KnownMember(user_id=9, last_name="Weasley", first_name="Ginny", birth_date="2013-08-11", licence="")
GINNY_ELDER = KnownMember(user_id=10, last_name="Weasley", first_name="Ginny", birth_date="1981-08-11", licence="")


@pytest.mark.parametrize(
    ("overrides", "members", "candidates", "reason_word"),
    [
        ({"last_name": "Weazley", "licence": "123456"}, (GINNY, LUNA), [7], "licence"),
        ({"last_name": "Weasley", "birth_date": "2013-09-11"}, (GINNY, LUNA), [7], "naissance"),
        ({"last_name": "Weasley"}, (GINNY, GINNY_TWIN), [7, 9], "plusieurs"),
        ({"last_name": "Weasley", "licence": "654321"}, (GINNY, KnownMember(11, "Potter", "Harry", "1980-07-31", "654321")), [7, 11],
         "plusieurs"),
        ({"last_name": "Weasley", "birth_date": "", "birth_date_raw": "?"}, (GINNY, GINNY_ELDER), [7, 10], "naissance"),
        ({"last_name": "Granger", "first_name": "Hermione", "birth_date": "", "birth_date_raw": ""}, (GINNY,), [], "naissance"),
    ],
)
def test_an_ambiguous_identity_is_to_review_with_its_candidates(
        overrides: dict[str, str], members: tuple[KnownMember, ...], candidates: list[int], reason_word: str) -> None:
    [entry] = _plan(_record(9001, **overrides), members=members).entries

    assert entry.bucket == Bucket.TO_REVIEW
    assert [member.user_id for member in entry.candidates] == candidates
    assert reason_word in entry.reason.lower()


def test_a_registration_without_birth_date_is_never_new() -> None:
    [entry] = _plan(_record(9001, last_name="Granger", first_name="Hermione", birth_date="", licence="")).entries

    assert entry.bucket == Bucket.TO_REVIEW
    assert not entry.can_create


def _review_plan() -> ImportPlan:
    return _plan(_record(1, last_name="Weasley"), members=(GINNY, GINNY_TWIN, LUNA))


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("link:9", (WriteAction.ATTACH, 9)),
        ("create", (WriteAction.CREATE, None)),
    ],
)
def test_the_choice_on_a_row_to_review_is_applied(choice: str, expected: tuple[WriteAction, int | None]) -> None:
    [write] = apply_decisions(_review_plan(), {1: Decision(Bucket.TO_REVIEW, choice)})

    assert (write.action, write.entry.member_id) == expected


def test_skipping_a_row_to_review_writes_nothing() -> None:
    assert apply_decisions(_review_plan(), {1: Decision(Bucket.TO_REVIEW, "skip")}) == []


@pytest.mark.parametrize("choice", ["link:8", "link:abc", "import"])
def test_a_link_to_a_member_who_is_not_a_candidate_is_rejected(choice: str) -> None:
    with pytest.raises(StaleDecisions):
        apply_decisions(_review_plan(), {1: Decision(Bucket.TO_REVIEW, choice)})


def test_a_row_without_birth_date_cannot_be_created() -> None:
    plan = _plan(_record(1, last_name="Granger", first_name="Hermione", birth_date="", licence=""))

    with pytest.raises(StaleDecisions):
        apply_decisions(plan, {1: Decision(Bucket.TO_REVIEW, "create")})


# ---------------------------------------------------------------------------
# Changes on HelloAsso: status, amount or tariff that HelloAsso changed since the last import
# ---------------------------------------------------------------------------
def _imported(**overrides: object) -> KnownPurchase:
    """Item 9001, imported as Processed / Loisir collège / 150 €, values unchanged since unless overridden."""
    return _purchase(30, 7, helloasso_item_id=9001, helloasso_status="Processed", helloasso_tarif="Loisir collège",
                     helloasso_amount=150.0, **overrides)


@pytest.mark.parametrize(
    ("helloasso", "expected"),
    [
        ({"status": "Refunded"}, [("status", "Processed", "Processed", "Refunded")]),
        ({"tarif_name": "Compétition U13", "amount": 200.0},
         [("tarif_name", "Loisir collège", "Loisir collège", "Compétition U13"), ("amount", "150.00", "150.00", "200.00")]),
    ],
)
def test_a_change_made_on_helloasso_only_is_proposed(helloasso: dict[str, object], expected: list[tuple[str, str, str, str]]) -> None:
    [entry] = _plan(_record(9001, **helloasso), purchases=(_imported(),)).entries

    assert (entry.bucket, entry.member_id, entry.purchase_id) == (Bucket.UPDATED, 7, 30)
    assert [(c.field, c.crm, c.before, c.after) for c in entry.changes] == expected


def test_a_change_made_in_the_crm_only_is_never_proposed() -> None:
    [entry] = _plan(_record(9001), purchases=(_imported(status="Terminé", amount=120.0),)).entries

    assert (entry.bucket, entry.changes) == (Bucket.ALREADY_IMPORTED, ())


def test_a_value_changed_on_both_sides_is_to_review_with_both_values() -> None:
    [entry] = _plan(_record(9001, status="Refunded"), purchases=(_imported(status="Terminé"),)).entries

    assert entry.bucket == Bucket.TO_REVIEW
    assert [(c.field, c.crm, c.before, c.after) for c in entry.changes] == [("status", "Terminé", "Processed", "Refunded")]
    assert entry.member_id == 7


def test_accepting_a_change_writes_an_update() -> None:
    plan = _plan(_record(9001, status="Refunded"), _record(9002, order_ref="ORD-9002", last_name="Lovegood", first_name="Luna",
                                                             birth_date="2012-02-13", status="Refunded"),
                 purchases=(_imported(), _purchase(31, 8, order_ref="ORD-9002", helloasso_item_id=9002, helloasso_status="Processed",
                                                   helloasso_tarif="Loisir collège", helloasso_amount=150.0, status="Terminé")))

    writes = apply_decisions(plan, {9001: Decision(Bucket.UPDATED, "import"), 9002: Decision(Bucket.TO_REVIEW, "import")})

    assert [(w.item_id, w.action) for w in writes] == [(9001, WriteAction.UPDATE), (9002, WriteAction.UPDATE)]
