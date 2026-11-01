"""Competitions screen, coaches and admins: the competitors of a competition. Counters and filters, « Participe »,
withdrawal of a competitor who paid (money carried over or lost), manual payment, check-in, removal, adding members
(frontend/src/pages/competitions/detail/CompetitionDetail.vue, plan phase 11)."""
import datetime

import pytest
from playwright.sync_api import expect

from helpers.competitions import open_competition, open_screen, participant_card, toast
from helpers.data import eventually, unique_name
from helpers.dialogs import accept_dialogs


def _iso(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


@pytest.fixture(scope="module")
def members(test_data):
    """Competition-group members by role in the fixture competition. Every counter gets a different
    value (participe 3, en attente 2, payé 1) so that mixing two of them up cannot go unnoticed."""
    found = test_data.competition_group()
    assert len(found) >= 5, "the seed creates competition-group members"
    return {"paid": found[0], "unpaid": found[1], "unpaid_2": found[2], "invited": found[3], "outsider": found[4]}


@pytest.fixture
def competition(test_data, members):
    listed = [members[k]["id"] for k in ("paid", "unpaid", "unpaid_2", "invited")]
    nom = unique_name("E2E Participants")
    cid = test_data.create_competition(nom, date=_iso(40), prix=12, participants=listed, selected=listed[:3])
    test_data.mark_paid(cid, members["paid"]["id"], 12.0, order_ref="E2E-PAID")
    return {"id": cid, "nom": nom}


def _participant(test_data, competition, member) -> dict:
    doc = test_data.competition(competition["id"])
    return next(p for p in doc["participants"] if p["adherent_id"] == member["id"])


def _assert_stored(test_data, competition, member, **expected):
    def check():
        stored = _participant(test_data, competition, member)
        assert {key: stored[key] for key in expected} == expected
    eventually(check)


def test_counters_and_filters(mobile_page, competition, members):
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    expect(page.get_by_test_id("filter-selected")).to_have_text("✅ Participe : Oui (3)")
    expect(page.get_by_test_id("filter-unpaid")).to_have_text("⏳ Paiement en attente (2)")
    cards = page.get_by_test_id("participant-card")
    expect(cards).to_have_count(4)
    expect(participant_card(page, members["paid"]).get_by_test_id("payment-badge")).to_have_text("Payé (12 €)")
    expect(participant_card(page, members["unpaid"]).get_by_test_id("payment-badge")).to_have_text("En attente")
    expect(participant_card(page, members["invited"]).get_by_test_id("payment-badge")).to_have_text("Non invité")

    page.get_by_test_id("filter-selected").click()
    expect(cards).to_have_count(3)
    page.get_by_test_id("filter-unpaid").click()
    expect(cards).to_have_count(2)
    expect(participant_card(page, members["paid"])).to_have_count(0)
    page.get_by_test_id("filter-notInvited").click()
    expect(cards).to_have_count(1)
    page.get_by_test_id("filter-all").click()
    page.get_by_test_id("participant-search").fill(members["invited"]["prenom"])
    expect(participant_card(page, members["invited"])).to_be_visible()


def test_select_invited_member(mobile_page, test_data, competition, members):
    invited = members["invited"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    participant_card(page, invited).get_by_test_id("participe-switch").click()
    expect(page.get_by_test_id("filter-selected")).to_have_text("✅ Participe : Oui (4)")
    expect(page.get_by_test_id("filter-unpaid")).to_have_text("⏳ Paiement en attente (3)")
    expect(participant_card(page, invited).get_by_test_id("payment-badge")).to_have_text("En attente")
    _assert_stored(test_data, competition, invited, selectionne=True, statut_paiement="en_attente")


def test_unselecting_paid_member_needs_a_decision(mobile_page, test_data, competition, members):
    paid = members["paid"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    participant_card(page, paid).get_by_test_id("participe-switch").click()
    dialog = page.get_by_test_id("withdraw-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("12,00 €")

    page.get_by_test_id("withdraw-ok").click()
    expect(page.get_by_test_id("withdraw-error")).to_contain_text("commentaire est obligatoire")
    page.get_by_test_id("withdraw-perdu").check()
    page.get_by_test_id("withdraw-note").fill("Injured")
    page.get_by_test_id("withdraw-ok").click()

    expect(dialog).to_be_hidden()
    card = participant_card(page, paid)
    expect(card.get_by_test_id("payment-badge")).to_contain_text("Annulé — perdu")
    expect(card).to_contain_text("Injured")
    expect(card.get_by_test_id("participe-switch")).not_to_be_checked()
    _assert_stored(test_data, competition, paid, selectionne=False, statut_paiement="annule_perdu", note_paiement="Injured")


def test_closing_the_withdrawal_keeps_the_paid_member(mobile_page, competition, members):
    paid = members["paid"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    participant_card(page, paid).get_by_test_id("participe-switch").click()
    page.get_by_test_id("withdraw-cancel").click()
    expect(page.get_by_test_id("withdraw-dialog")).to_be_hidden()
    expect(participant_card(page, paid).get_by_test_id("participe-switch")).to_be_checked()
    expect(participant_card(page, paid).get_by_test_id("payment-badge")).to_have_text("Payé (12 €)")


def test_add_member_outside_the_list(mobile_page, test_data, competition, members):
    outsider = members["outsider"]
    page = open_screen(mobile_page)
    open_competition(page, competition["nom"])
    page.get_by_test_id("add-competitor-btn").click()
    page.get_by_test_id("member-search").fill(outsider["nom"][:4])
    result = page.get_by_test_id("member-result").filter(has_text=f"{outsider['nom']} {outsider['prenom']}")
    result.get_by_test_id("member-add").click()
    expect(participant_card(page, outsider)).to_be_visible()
    expect(page.get_by_test_id("member-search")).to_have_value("")  # the dialog stays open for the next one
    expect(page.get_by_test_id("filter-selected")).to_have_text("✅ Participe : Oui (4)")
    _assert_stored(test_data, competition, outsider, selectionne=True)


def test_load_competition_group(mobile_page, test_data):
    nom = unique_name("E2E Group")
    cid = test_data.create_competition(nom, date=_iso(41))
    group = test_data.competition_group()
    page = open_screen(mobile_page)
    open_competition(page, nom)
    expect(page.get_by_test_id("participant-card")).to_have_count(0)
    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("load-group").click()
    expect(page.get_by_test_id("participant-card")).to_have_count(len(group))
    expect(page.get_by_test_id("filter-selected")).to_have_text("✅ Participe : Oui (0)")

    def loaded():
        assert {p["statut_paiement"] for p in test_data.competition(cid)["participants"]} == {"non_invite"}
    eventually(loaded)

    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("load-group").click()
    expect(toast(page)).to_contain_text("déjà présents")

    # Never invited: removed all at once
    accept_dialogs(page)
    page.get_by_test_id("filter-notInvited").click()
    page.get_by_test_id("detail-more").click()
    page.get_by_test_id("remove-not-invited").click()
    expect(page.get_by_test_id("participant-card")).to_have_count(0)

    def removed():
        assert test_data.competition(cid)["participants"] == []
    eventually(removed)


# ---------------------------------------------------------------------------
# Competitors workflow on desktop: manual payment, withdrawal (credit kept or lost), check-in, removal
# ---------------------------------------------------------------------------
@pytest.fixture
def workflow(test_data, members):
    """A competition with a paid competitor and an unpaid one, opened by the admin."""
    paid, unpaid = members["paid"], members["unpaid"]
    nom = unique_name("E2E Workflow")
    cid = test_data.create_competition(nom, date=_iso(28), prix=12, participants=[paid["id"], unpaid["id"]],
                                       selected=[paid["id"], unpaid["id"]])
    test_data.mark_paid(cid, paid["id"], 12.0, order_ref="E2E-PAID")
    return {"id": cid, "nom": nom, "paid": paid, "unpaid": unpaid}


def _open_workflow(page, workflow):
    open_screen(page, "admin", "/bureau/competitions")
    open_competition(page, workflow["nom"])


def test_manual_payment(page, test_data, workflow):
    _open_workflow(page, workflow)
    card = participant_card(page, workflow["unpaid"])
    expect(card.get_by_test_id("payment-badge")).to_have_text("En attente")
    card.get_by_test_id("manual-payment").click()
    expect(page.get_by_test_id("payment-amount")).to_have_value("12")
    page.get_by_test_id("payment-amount").fill("12,5")
    page.get_by_test_id("payment-ok").click()
    expect(toast(page)).to_contain_text("Paiement manuel de 12.5 € enregistré")
    expect(card.get_by_test_id("payment-badge")).to_have_text("Payé (12.5 €)")
    _assert_stored(test_data, workflow, workflow["unpaid"], statut_paiement="paye", montant_paye=12.5, commande_helloasso="Règlement manuel")


def test_paid_competitor_cannot_be_removed(page, workflow):
    _open_workflow(page, workflow)
    card = participant_card(page, workflow["paid"])
    expect(card.get_by_test_id("payment-badge")).to_have_text("Payé (12 €)")
    expect(card).to_contain_text("E2E-PAID")
    expect(card.get_by_test_id("remove")).to_have_count(0)
    expect(card.get_by_test_id("withdraw")).to_be_visible()


@pytest.mark.parametrize("mode, badge, status", [("reporte", "Annulé — report (12 €)", "annule_reporte"), ("perdu", "Annulé — perdu (12 €)", "annule_perdu")])
def test_withdrawal_of_paid_competitor(page, test_data, workflow, mode, badge, status):
    _open_workflow(page, workflow)
    accept_dialogs(page)
    card = participant_card(page, workflow["paid"])
    card.get_by_test_id("withdraw").click()
    page.get_by_test_id(f"withdraw-{mode}").check()
    page.get_by_test_id("withdraw-note").fill("Injured")
    page.get_by_test_id("withdraw-ok").click()
    expect(card.get_by_test_id("payment-badge")).to_have_text(badge)
    expect(card.get_by_test_id("participe-switch")).not_to_be_checked()
    _assert_stored(test_data, workflow, workflow["paid"], statut_paiement=status, selectionne=False, montant_paye=12)

    # A withdrawal entered by mistake can be undone
    card.get_by_test_id("restore").click()
    expect(card.get_by_test_id("payment-badge")).to_have_text("Payé (12 €)")
    _assert_stored(test_data, workflow, workflow["paid"], statut_paiement="paye", selectionne=True)


def test_checked_in_competitor_is_locked(mobile_page, test_data, workflow):
    """On a phone: the wide table has no « Présent » column."""
    page = mobile_page
    _open_workflow(page, workflow)
    card = participant_card(page, workflow["paid"])
    card.get_by_test_id("present-switch").click()
    expect(card.get_by_test_id("on-site")).to_contain_text("Sur place")
    expect(card.get_by_test_id("withdraw")).to_have_count(0)
    expect(card.get_by_test_id("present-switch")).to_be_checked()
    _assert_stored(test_data, workflow, workflow["paid"], present=True)


def test_remove_unpaid_competitor(page, test_data, workflow):
    _open_workflow(page, workflow)
    accept_dialogs(page)
    participant_card(page, workflow["unpaid"]).get_by_test_id("remove").click()
    expect(participant_card(page, workflow["unpaid"])).to_have_count(0)

    def removed():
        assert [p["adherent_id"] for p in test_data.competition(workflow["id"])["participants"]] == [workflow["paid"]["id"]]
    eventually(removed)
