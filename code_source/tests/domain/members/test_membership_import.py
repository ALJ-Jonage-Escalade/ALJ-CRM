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
    PlanEntry,
    StaleDecisions,
    WriteAction,
    apply_decisions,
    plan_membership_import,
    season_membership,
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


# ---------------------------------------------------------------------------
# Decisions applier: the admin's decisions, keyed by HelloAsso item id, become the writes
# ---------------------------------------------------------------------------
def _new_plan() -> ImportPlan:
    return plan_membership_import([_record(1), _record(2, first_name="Ron"), _record(3, last_name="")], season=SEASON,
                                  campaign_slug=CAMPAIGN)


@pytest.mark.parametrize("decisions", [{2: Decision(Bucket.NEW, "skip")}, {}], ids=["unchecked", "no decision"])
def test_only_the_checked_new_rows_are_created(decisions: dict[int, Decision]) -> None:
    """No decision: a registration that appeared on HelloAsso after the preview, never seen by the admin."""
    writes = apply_decisions(_new_plan(), {1: Decision(Bucket.NEW, "import"), **decisions})

    assert [(write.item_id, write.action) for write in writes] == [(1, WriteAction.CREATE)]


@pytest.mark.parametrize(
    "decisions",
    [
        {99: Decision(Bucket.NEW, "import")},  # unknown item
        {1: Decision(Bucket.RENEWAL, "import")},  # the row changed bucket since the preview
        {3: Decision(Bucket.BLOCKED, "import")},  # a blocked row cannot be imported
    ],
)
def test_stale_or_invalid_decisions_are_rejected(decisions: dict[int, Decision]) -> None:
    with pytest.raises(StaleDecisions):
        apply_decisions(_new_plan(), decisions)


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
        ({"last_name": "WEASLEY", "licence": "123456", "birth_date": "", "birth_date_raw": "?"}, "no birth date, unique licence"),
        ({"last_name": "Weasley", "licence": "999999"}, "same name and birth date, licence unknown to the club"),
    ],
)
def test_a_known_person_is_a_renewal(overrides: dict[str, str], why: str) -> None:
    [entry] = _plan(_record(9001, **overrides)).entries

    assert (entry.bucket, entry.member_id) == (Bucket.RENEWAL, 7), why


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
    ],
)
def test_an_ambiguous_identity_is_to_review_with_its_candidates(
        overrides: dict[str, str], members: tuple[KnownMember, ...], candidates: list[int], reason_word: str) -> None:
    [entry] = _plan(_record(9001, **overrides), members=members).entries

    assert entry.bucket == Bucket.TO_REVIEW
    assert [member.user_id for member in entry.candidates] == candidates
    assert reason_word in entry.reason.lower()


@pytest.mark.parametrize(
    "overrides",
    [
        {"first_name": "Ginevra"},  # first name typed otherwise
        {"last_name": "Weazley"},  # last name misspelled
        {"last_name": "Ginny", "first_name": "Weasley"},  # last and first name swapped
    ],
)
def test_a_close_name_with_the_same_birth_date_is_to_review_not_new(overrides: dict[str, str]) -> None:
    [entry] = _plan(_record(9001, **overrides)).entries

    assert entry.bucket == Bucket.TO_REVIEW
    assert [member.user_id for member in entry.candidates] == [7]
    assert "proche" in entry.reason.lower()
    assert entry.can_create  # another person after all: the admin may still create them


@pytest.mark.parametrize(
    "overrides",
    [
        {"last_name": "Granger", "first_name": "Hermione"},  # same birth date, another name
        {"first_name": "Ron", "birth_date": "2011-03-01"},  # a sibling: same last name, another birth date
    ],
)
def test_a_person_without_a_close_name_and_birth_date_is_new(overrides: dict[str, str]) -> None:
    assert _plan(_record(9001, **overrides)).entries[0].bucket == Bucket.NEW


@pytest.mark.parametrize(("birth_date", "typed", "issue"), [
    ("", "", "missing"),
    ("", "11/08/13", "unreadable"),
    ("1026-01-01", "01/01/1026", "too_old"),  # read, but implausible: never reaches the FFME
    ("2026-08-11", "11/08/2026", "too_young"),  # the registration year typed in
], ids=["missing", "unreadable", "too old", "too young"])
def test_a_registration_without_a_plausible_birth_date_is_never_new(birth_date: str, typed: str, issue: str) -> None:
    plan = _plan(_record(9001, last_name="Granger", first_name="Hermione", birth_date=birth_date, birth_date_raw=typed, licence=""))

    assert plan.entries[0].bucket == Bucket.TO_REVIEW
    assert not plan.entries[0].can_create
    assert [(found.field, found.code, found.blocking) for found in plan.entries[0].issues
            if found.field == "birth_date"] == [("birth_date", issue, True)]
    with pytest.raises(StaleDecisions):
        apply_decisions(plan, {9001: Decision(Bucket.TO_REVIEW, "create")})


def _review_plan() -> ImportPlan:
    return _plan(_record(1, last_name="Weasley"), members=(GINNY, GINNY_TWIN, LUNA))


def test_a_row_to_review_whose_identity_is_taken_cannot_be_created() -> None:
    """The member writers find people by name, first name and birth date: "create" would attach to that member."""
    plan = _plan(_record(1, last_name="Weasley", licence="654321"), members=(GINNY, KnownMember(11, "Potter", "Harry", "1980-07-31", "654321")))

    assert not plan.entries[0].can_create
    with pytest.raises(StaleDecisions):
        apply_decisions(plan, {1: Decision(Bucket.TO_REVIEW, "create")})


@pytest.mark.parametrize("choice", ["link:8", "import"])
def test_a_link_to_a_member_who_is_not_a_candidate_is_rejected(choice: str) -> None:
    with pytest.raises(StaleDecisions):
        apply_decisions(_review_plan(), {1: Decision(Bucket.TO_REVIEW, choice)})


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


def test_accepting_a_change_writes_an_update() -> None:
    plan = _plan(_record(9001, status="Refunded"), _record(9002, order_ref="ORD-9002", last_name="Lovegood", first_name="Luna",
                                                             birth_date="2012-02-13", status="Refunded"),
                 purchases=(_imported(), _purchase(31, 8, order_ref="ORD-9002", helloasso_item_id=9002, helloasso_status="Processed",
                                                   helloasso_tarif="Loisir collège", helloasso_amount=150.0, status="Terminé")))

    writes = apply_decisions(plan, {9001: Decision(Bucket.UPDATED, "import"), 9002: Decision(Bucket.TO_REVIEW, "import")})

    assert [(w.item_id, w.action) for w in writes] == [(9001, WriteAction.UPDATE), (9002, WriteAction.UPDATE)]


# ---------------------------------------------------------------------------
# Attach by hand: a registration given to any member (a parent registered their child under their own name)
# ---------------------------------------------------------------------------
MOLLY = _record(1, first_name="Molly", birth_date="1950-10-30")


def test_a_new_row_attached_to_a_member_without_membership_this_season_adds_one() -> None:
    plan = _plan(MOLLY, purchases=(_purchase(30, 7, season="2025-2026", helloasso_item_id=500),))

    [write] = apply_decisions(plan, {1: Decision(Bucket.NEW, "attach:7", comment="Inscrite par sa mère")})

    assert (write.action, write.entry.member_id, write.entry.purchase_id, write.comment) == (
        WriteAction.ASSIGN, 7, None, "Inscrite par sa mère")


def test_an_attach_takes_over_the_manual_membership_of_the_season() -> None:
    manual = _purchase(31, 7, order_ref="MANUEL-20261101-101500", status="Validé", amount=0.0)
    plan = _plan(MOLLY, purchases=(_purchase(30, 7, season="2025-2026", helloasso_item_id=500), manual))

    [write] = apply_decisions(plan, {1: Decision(Bucket.NEW, "attach:7", comment="Inscrite par sa mère")})

    assert (write.action, write.entry.member_id, write.entry.purchase_id) == (WriteAction.ASSIGN, 7, 31)


def _manual(purchase_id: int, user_id: int = 7) -> KnownPurchase:
    return _purchase(purchase_id, user_id, order_ref=f"MANUEL-{purchase_id}", status="Validé", amount=0.0)


@pytest.mark.parametrize(("records", "purchases", "decisions", "why"), [
    ((MOLLY,), (), {1: Decision(Bucket.NEW, "attach:7", comment="  ")}, "commentaire"),
    ((MOLLY,), (_manual(31), _manual(32)), {1: Decision(Bucket.NEW, "attach:7", comment="Mère")}, "plusieurs adhésions"),
    ((MOLLY,), (_purchase(30, 7, helloasso_item_id=500),), {1: Decision(Bucket.NEW, "attach:7", comment="Mère")}, "déjà une adhésion HelloAsso"),
    ((MOLLY, _record(2, first_name="Arthur", birth_date="1950-02-06")), (),
     {1: Decision(Bucket.NEW, "attach:7", comment="Mère"), 2: Decision(Bucket.NEW, "attach:7", comment="Père")}, "une autre inscription"),
    ((MOLLY, _record(2)), (), {1: Decision(Bucket.NEW, "attach:7", comment="Mère"), 2: Decision(Bucket.RENEWAL, "import")},
     "une autre inscription"),
    ((MOLLY,), (), {1: Decision(Bucket.NEW, "attach:99", comment="Mère")}, "introuvable"),
], ids=["no comment", "several manual memberships", "helloasso membership", "chosen twice", "renewed in the same import", "unknown member"])
def test_an_attach_is_refused(records: tuple[MembershipRecord, ...], purchases: tuple[KnownPurchase, ...],
                              decisions: dict[int, Decision], why: str) -> None:
    with pytest.raises(StaleDecisions, match=why):
        apply_decisions(_plan(*records, purchases=purchases), decisions)


def test_a_purchase_back_filled_by_the_import_is_a_helloasso_membership_not_a_manual_one() -> None:
    """A former import's purchase, recognised by its order: the attach must not take it over."""
    plan = _plan(MOLLY, _record(2, order_ref="ORD-OLD"), purchases=(_purchase(31, 7, order_ref="ORD-OLD"),))

    with pytest.raises(StaleDecisions, match="déjà une adhésion HelloAsso"):
        apply_decisions(plan, {1: Decision(Bucket.NEW, "attach:7", comment="Mère")})


@pytest.mark.parametrize(("purchases", "bucket"), [
    ((), Bucket.RENEWAL),
    ((_purchase(30, 7, helloasso_item_id=1, amount=120.0),), Bucket.UPDATED),
], ids=["renewal", "updated"])
def test_which_rows_can_be_attached(purchases: tuple[KnownPurchase, ...], bucket: Bucket) -> None:
    """New, renewal and to-review identity rows can; an imported row (updated, already imported, conflict) cannot."""
    plan = _plan(_record(1), members=(GINNY, LUNA), purchases=purchases)
    assert plan.entries[0].bucket == bucket
    decision = Decision(bucket, "attach:8", comment="Erreur de nom")

    if bucket == Bucket.RENEWAL:
        [write] = apply_decisions(plan, {1: decision})
        assert (write.action, write.entry.member_id) == (WriteAction.ASSIGN, 8)
    else:
        with pytest.raises(StaleDecisions):
            apply_decisions(plan, {1: decision})


def test_a_row_to_review_can_be_attached_to_a_member_who_is_not_a_candidate() -> None:
    [write] = apply_decisions(_review_plan(), {1: Decision(Bucket.TO_REVIEW, "attach:8", comment="Erreur de nom")})

    assert (write.action, write.entry.member_id) == (WriteAction.ASSIGN, 8)


@pytest.mark.parametrize(("member", "attached_to"), [
    (replace(GINNY, first_name="Ginny"), None),
    (replace(GINNY, first_name="Gínny "), None),
    (GINNY, GINNY),
], ids=["same name", "same name, other accents", "attached by hand"])
def test_an_imported_row_names_the_member_it_is_attached_to_when_the_names_differ(member: KnownMember, attached_to: KnownMember) -> None:
    record = MOLLY if attached_to else _record(1)
    [entry] = _plan(record, members=(member,), purchases=(_purchase(30, 7, helloasso_item_id=1),)).entries

    assert (entry.bucket, entry.attached_to) == (Bucket.ALREADY_IMPORTED, attached_to)
    if attached_to:
        assert "rattachée à WEASLEY Ginny" in entry.reason


@pytest.mark.parametrize(("purchases", "expected"), [
    ((), "none"),
    ((_purchase(30, 7, season="2025-2026", helloasso_item_id=500),), "none"),
    ((_manual(31),), "manual"),
    ((_manual(31), _manual(32)), "several_manual"),
    ((_purchase(30, 7, helloasso_item_id=500),), "helloasso"),
], ids=["no purchase", "another season", "manual", "several manual", "helloasso"])
def test_the_season_membership_of_each_member_is_known_to_the_preview(purchases: tuple[KnownPurchase, ...], expected: str) -> None:
    plan = _plan(_record(2, last_name="Potter"), purchases=purchases)

    assert season_membership(plan, 7).kind == expected


# ---------------------------------------------------------------------------
# Data checks: the values the import would store, normalised, with their issues
# ---------------------------------------------------------------------------
def _issues(entry: PlanEntry) -> list[tuple[str, str]]:
    return [(issue.field, issue.code) for issue in entry.issues]


def test_a_new_member_is_written_with_normalised_phones() -> None:
    record = _record(custom_fields={"Téléphone ": "+33 6 12 34 56 78",
                                    "Personne à prévenir en cas d'urgence - Téléphone": "0033612345679"})

    [entry] = plan_membership_import([record], season=SEASON, campaign_slug=CAMPAIGN).entries

    fields = entry.record.legacy_fields()
    assert (fields["champ_Téléphone "], fields["champ_Personne à prévenir en cas d'urgence - Téléphone"]) == ("06 12 34 56 78",
                                                                                                         "06 12 34 56 79")
    assert [field for field, _code in _issues(entry) if "phone" in field] == []


def test_a_registration_with_problems_stays_importable() -> None:
    record = _record(custom_fields={"Téléphone ": "061234567"})

    [entry] = plan_membership_import([record], season=SEASON, campaign_slug=CAMPAIGN).entries

    assert entry.bucket == Bucket.NEW
    assert ("phone", "invalid") in _issues(entry)
    assert [write.action for write in apply_decisions(_plan(record, members=()), {9001: Decision(Bucket.NEW, "import")})] == [WriteAction.CREATE]


@pytest.mark.parametrize(("crm_phone", "expected"), [
    ("06 12 34 56 78", []),  # the CRM value is kept: the HelloAsso typo is never written
    ("", [("phone", "invalid")]),  # blank in the CRM: the HelloAsso value fills it
])
def test_a_renewal_is_checked_on_the_values_it_will_keep(crm_phone: str, expected: list[tuple[str, str]]) -> None:
    record = _record(custom_fields={"Téléphone ": "061234567"})

    [entry] = _plan(record, members=(replace(GINNY, phone=crm_phone),)).entries

    assert entry.bucket == Bucket.RENEWAL
    assert [issue for issue in _issues(entry) if issue[0] == "phone"] == expected


EMAIL_FIELD = "Adresse mail pour la réception des informations du club"
EMAIL_2_FIELD = "Deuxième adresse mail pour la réception des informations du club"


def test_the_emails_are_checked_with_the_domain_check_and_written_normalised() -> None:
    record = _record(custom_fields={EMAIL_FIELD: "Molly@Terrier.Example", EMAIL_2_FIELD: "arthur@gmial.com"})

    [entry] = plan_membership_import([record], season=SEASON, campaign_slug=CAMPAIGN,
                                     domain_accepts_mail=lambda domain: domain != "gmial.com").entries

    assert [issue for issue in _issues(entry) if issue[0].startswith("email")] == [("email_2", "no_mail_domain")]
    assert entry.record.legacy_fields()[f"champ_{EMAIL_FIELD}"] == "Molly@terrier.example"


def test_a_renewal_is_checked_on_the_emails_the_crm_keeps() -> None:
    record = _record(custom_fields={EMAIL_FIELD: "molly terrier.example"})

    [entry] = _plan(record, members=(replace(GINNY, email="molly@terrier.example"),)).entries

    assert [issue for issue in _issues(entry) if issue[0].startswith("email")] == []
