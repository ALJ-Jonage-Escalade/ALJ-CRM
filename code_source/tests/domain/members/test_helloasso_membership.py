"""HelloAsso membership item mapper: a raw HelloAsso v5 item becomes a flat membership record (fake data only)."""

from __future__ import annotations

from typing import Any

import pytest

from domain.members.helloasso_membership import (
    map_membership_item,
    map_membership_items,
    parse_membership_campaign,
    season_guard,
)


def _item(**overrides: Any) -> dict[str, Any]:  # Any: raw HelloAsso JSON
    item: dict[str, Any] = {
        "id": 9001,
        "type": "Membership",
        "state": "Processed",
        "name": "Loisir collège",
        "amount": 15000,
        "order": {"id": 501, "date": "2026-09-01T10:00:00+02:00"},
        "user": {"firstName": "Ginny", "lastName": "Weasley"},
        "payer": {"firstName": "Molly", "lastName": "Weasley", "email": "molly@terrier.example"},
        "options": [],
        "customFields": [
            {"name": "Date de naissance de l'adhérent", "answer": "11/08/2013"},
            {"name": "Numéro de Licence FFME (6 chiffres)", "answer": "123 456"},
            {"name": "Ville", "answer": "Jonage"},
        ],
    }
    item.update(overrides)
    return item


def test_map_membership_item_reads_identity_order_and_payment() -> None:
    record = map_membership_item(_item())

    assert record.item_id == 9001
    assert (record.order_ref, record.order_date) == ("501", "2026-09-01T10:00:00+02:00")
    assert (record.status, record.tarif_name, record.amount) == ("Processed", "Loisir collège", 150.0)
    assert (record.last_name, record.first_name) == ("Weasley", "Ginny")
    assert (record.payer_last_name, record.payer_first_name, record.payer_email) == ("Weasley", "Molly", "molly@terrier.example")
    assert record.birth_date == "2013-08-11"
    assert record.licence == "123456"
    assert record.custom_fields["Ville"] == "Jonage"


@pytest.mark.parametrize(
    ("custom_field", "expected_licence"),
    [
        ({"name": "Numéro de Licence FFME (6 chiffres)", "answer": "654321"}, "654321"),
        ({"name": "Numéro de Licence FFME (6 chiffres)", "value": "654321"}, "654321"),
        ({"name": "Numéro de Licence FFME (6 chiffres)", "answer": "", "value": "654321"}, "654321"),
    ],
)
def test_map_membership_item_reads_custom_fields_from_answer_or_value(custom_field: dict[str, str], expected_licence: str) -> None:
    assert map_membership_item(_item(customFields=[custom_field])).licence == expected_licence


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("11/08/2013", "2013-08-11"),
        ("2013-08-11", "2013-08-11"),
        ("2013-08-11T00:00:00", "2013-08-11"),
        ("onze août", ""),
        # Never guessed: a two-digit year or a dash format may be misread
        ("11/08/13", ""),
        ("11-08-2013", ""),
    ],
)
def test_map_membership_item_parses_the_birth_date(typed: str, expected: str) -> None:
    record = map_membership_item(_item(customFields=[{"name": "Date de naissance de l'adhérent", "value": typed}]))

    assert (record.birth_date, record.birth_date_raw) == (expected, typed.strip())


def test_map_membership_items_keeps_the_registrations_only() -> None:
    items = [_item(id=1), _item(id=2, type="Donation"), _item(id=3, type="Registration")]

    assert [record.item_id for record in map_membership_items(items)] == [1, 3]


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("adhesion-escalade-2026-2027", ("Membership", "adhesion-escalade-2026-2027")),
        ("https://www.helloasso.com/associations/alj/adhesions/adhesion-escalade-2026-2027", ("Membership", "adhesion-escalade-2026-2027")),
    ],
)
def test_parse_membership_campaign_reads_a_slug_or_a_helloasso_url(reference: str, expected: tuple[str, str]) -> None:
    campaign = parse_membership_campaign(reference)

    assert (campaign.form_type, campaign.slug) == expected


@pytest.mark.parametrize(
    ("slug", "allowed"),
    [
        ("adhesion-escalade-2026-2027-amicale-laique-escalade-2", True),
        ("adhesion-escalade-2025-2026-amicale-laique-escalade-2", False),
    ],
)
def test_season_guard_refuses_a_campaign_of_another_season(slug: str, allowed: bool) -> None:
    reason = season_guard(slug, "2026-2027")

    assert (reason is None) == allowed
    if not allowed:
        assert "2026-2027" in str(reason)


def test_legacy_fields_feed_the_member_writers() -> None:
    item = _item(options=[{"name": "Assurance Base ++ (recommandée)", "amount": 1500}, {"name": "Option ski de piste", "amount": 300}],
                 customFields=[{"name": "Date de naissance de l'adhérent", "answer": "11/08/2013"},
                               {"name": "Téléphone ", "value": "0611223344"}])

    fields = map_membership_item(item).legacy_fields()

    assert fields["order_ref"] == "501"
    assert (fields["user_lastName"], fields["user_firstName"], fields["payer_email"]) == ("Weasley", "Ginny", "molly@terrier.example")
    assert (fields["status"], fields["tarif_name"], fields["amount"]) == ("Processed", "Loisir collège", 150.0)
    assert fields["champ_Date de naissance de l'adhérent"] == "2013-08-11"
    assert fields["champ_Téléphone "] == "0611223344"
    assert (fields["opt_Assurance Base ++"], fields["opt_Montant Assurance Base ++"]) == ("Oui", 15.0)
    assert (fields["opt_Assurance Option ski de piste"], fields["opt_Montant Assurance Option ski de piste"]) == ("Oui", 3.0)
    assert (fields["opt_Assurance Base"], fields["opt_Montant Assurance Base"]) == ("Non", 0.0)


def _payment(state: str, date: str = "2026-09-01T10:05:00+02:00", **overrides: Any) -> dict[str, Any]:  # Any: raw HelloAsso JSON
    payment: dict[str, Any] = {"id": 77, "date": date, "amount": 15000, "state": state, "refundOperations": []}
    payment.update(overrides)
    return payment


def test_map_membership_item_reads_the_payment_date() -> None:
    record = map_membership_item(_item(payments=[_payment("Authorized", "2026-09-03T08:00:00+02:00")]))

    assert (record.status, record.payment_date, record.refund_date) == ("Processed", "2026-09-03T08:00:00+02:00", "")


def test_map_membership_item_keeps_the_first_payment_of_an_instalment_plan() -> None:
    payments = [_payment("Pending", "2026-11-03T08:00:00+02:00"), _payment("Authorized", "2026-09-03T08:00:00+02:00")]

    assert map_membership_item(_item(payments=payments)).payment_date == "2026-09-03T08:00:00+02:00"


def test_map_membership_item_without_payment_has_no_payment_date() -> None:
    assert map_membership_item(_item()).payment_date == ""


@pytest.mark.parametrize("payment_state", ["Refunded", "Refunding"])
def test_map_membership_item_reads_a_refund_on_the_payments(payment_state: str) -> None:
    refund = {"id": 5, "amount": 15000, "status": "Processed", "meta": {"createdAt": "2026-10-14T09:30:00+02:00"}}
    payment = _payment(payment_state, refundOperations=[refund], meta={"updatedAt": "2026-10-15T00:00:00+02:00"})

    record = map_membership_item(_item(state="Processed", payments=[payment]))

    assert (record.status, record.refund_date) == (payment_state, "2026-10-14T09:30:00+02:00")


def test_map_membership_item_dates_a_refund_without_operation_by_the_payment_update() -> None:
    payment = _payment("Refunded", meta={"updatedAt": "2026-10-15T11:00:00+02:00"})

    assert map_membership_item(_item(payments=[payment])).refund_date == "2026-10-15T11:00:00+02:00"


def test_map_membership_item_is_not_refunded_while_a_payment_still_counts() -> None:
    payments = [_payment("Refunded"), _payment("Authorized")]

    record = map_membership_item(_item(payments=payments))

    assert (record.status, record.refund_date) == ("Processed", "")


def test_map_membership_item_keeps_a_cancellation_of_the_item() -> None:
    assert map_membership_item(_item(state="Canceled", payments=[_payment("Refunded")])).status == "Canceled"
