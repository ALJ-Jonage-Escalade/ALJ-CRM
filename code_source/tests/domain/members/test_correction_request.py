"""Correction requests to the families (domain/members/correction_request.py, issue #135). Fake data only."""

from __future__ import annotations

from domain.members.correction_request import CorrectionRequest, correction_requests
from domain.members.helloasso_membership import MembershipRecord
from domain.members.import_corrections import FieldCorrection
from domain.members.membership_import import plan_membership_import

SEASON = "2026-2027"
CAMPAIGN = "adhesion-escalade-2026-2027-amicale-laique-escalade-2"
EMAIL_FIELD = "Adresse mail pour la réception des informations du club"
GOOD = {"Téléphone ": "06 12 34 56 78", EMAIL_FIELD: "molly@terrier.example", "Pays": "France", "Nationalité": "Française"}


def _record(item_id: int, first_name: str, order_ref: str = "ORD-1", **custom_fields: str) -> MembershipRecord:
    return MembershipRecord(
        item_id=item_id, order_ref=order_ref, order_date="2026-09-01T10:00:00", status="Processed", tarif_name="Loisir collège",
        amount=150.0, last_name="Weasley", first_name=first_name, payer_last_name="Weasley", payer_first_name="Molly",
        payer_email="Molly@Terrier.example", birth_date="2013-08-11", birth_date_raw="11/08/2013", licence="",
        custom_fields={**GOOD, **custom_fields},
    )


def _requests(*records: MembershipRecord) -> list[CorrectionRequest]:
    return correction_requests(plan_membership_import(records, season=SEASON, campaign_slug=CAMPAIGN).entries)


def test_one_request_per_order_lists_the_problems_of_each_registration() -> None:
    ginny = _record(1, "Ginny", **{"Téléphone ": "061234567"})
    ron = _record(2, "Ron", **{"Pays": "Bretagne"})

    [request] = _requests(ginny, ron)

    assert (request.order_ref, request.payer_email, request.item_ids) == ("ORD-1", "Molly@Terrier.example", (1, 2))
    assert request.problems.splitlines() == [
        "Ginny WEASLEY :",
        "- Téléphone de l'adhérent invalide (« 061234567 »).",
        "",
        "Ron WEASLEY :",
        "- Pays non reconnu (« Bretagne »).",
    ]


def test_registrations_without_problems_and_other_orders_get_their_own_or_no_request() -> None:
    requests = _requests(_record(1, "Ginny"), _record(2, "Ron", "ORD-2", **{"Pays": ""}))

    assert [(request.order_ref, request.item_ids) for request in requests] == [("ORD-2", (2,))]


def test_the_primary_club_email_is_in_copy_when_valid_and_different_from_the_payers() -> None:
    other = _record(1, "Ginny", **{"Téléphone ": "", EMAIL_FIELD: "ginny@poudlard.example"})
    same = _record(2, "Ron", "ORD-2", **{"Téléphone ": "", EMAIL_FIELD: "molly@terrier.example"})
    invalid = _record(3, "Fred", "ORD-3", **{EMAIL_FIELD: "fred terrier.example"})

    copies = {request.order_ref: request.cc for request in _requests(other, same, invalid)}

    assert copies == {"ORD-1": ("ginny@poudlard.example",), "ORD-2": (), "ORD-3": ()}


def test_a_corrected_problem_is_not_asked_again() -> None:
    record = _record(1, "Ginny", **{"Téléphone ": "061234567", "Pays": "Bretagne"})
    phone_fix = FieldCorrection(field="phone", value="0612345678", helloasso_value="061234567", author="albus@poudlard.example", at="")
    entries = plan_membership_import([record], season=SEASON, campaign_slug=CAMPAIGN, corrections={1: {"phone": phone_fix}}).entries

    [request] = correction_requests(entries)

    assert "Téléphone" not in request.problems and "Bretagne" in request.problems

