"""HelloAsso payments: sync from the (fake) API, automatic and manual links, ignored lines (« HelloAsso » section of
the competitions screen, frontend/src/pages/competitions/helloasso/HelloAssoPane.vue), webhook notifications and the
membership dashboard."""
import re
import uuid

import pytest
from playwright.sync_api import expect

from helpers import helloasso
from helpers.competitions import go_to, open_competition, open_screen, participant_card, toast
from helpers.data import eventually, unique_name
from helpers.helloasso import item

# One fake HelloAsso state for the whole server: these tests run one after another (conftest.py)
pytestmark = pytest.mark.xdist_group("helloasso")


@pytest.fixture
def setup(test_data, fake_helloasso):
    """A competition with two invited members (with a licence) and three HelloAsso payments:
    one auto-linkable (licence + competition number), two that need a coach."""
    members = [m for m in test_data.competition_group() if m.get("licence_ffme")][:2]
    assert len(members) == 2, "the seed gives most members a licence number"
    number = "E2E-" + uuid.uuid4().hex[:6].upper()
    nom = unique_name("E2E HelloAsso")
    cid = test_data.create_competition(nom, date="2027-11-05", prix=15, id_ffme=number,
                                       participants=[m["id"] for m in members], selected=[members[0]["id"]])
    tag = uuid.uuid4().hex[:6]
    auto = item(members[0]["prenom"], members[0]["nom"], 15, licence=members[0]["licence_ffme"],
                competition_number=number)
    unknown_payer = item("Mundungus", f"Fletcher{tag}", 15, competition_number=number)
    no_competition = item("Gilderoy", f"Lockhart{tag}", 7.5)
    fake_helloasso.set([auto, unknown_payer, no_competition])
    return {"competition": {"id": cid, "nom": nom}, "members": members, "tag": tag,
            "auto": auto, "unknown_payer": unknown_payer, "no_competition": no_competition}


def _sync(page):
    go_to(page, "helloasso")
    page.get_by_test_id("ha-sync").click()
    expect(toast(page)).to_contain_text("Synchro terminée : 3 article(s)", timeout=20_000)


def _item_card(page, ha_item):
    """Card (table row on desktop) of a HelloAsso item, by its order number (members get payments in several tests)."""
    page.get_by_test_id("ha-filter-all").click()
    page.get_by_test_id("ha-search").fill(str(ha_item["order"]["id"]))
    return page.get_by_test_id("ha-item").filter(has_text=re.compile(rf"#{ha_item['order']['id']}(?!\d)"))


def _participant(test_data, setup, member) -> dict:
    return next(p for p in test_data.competition(setup["competition"]["id"])["participants"]
                if p["adherent_id"] == member["id"])


def _link(page, setup, ha_item, member, comment=""):
    _item_card(page, ha_item).get_by_test_id("ha-open").click()
    page.get_by_test_id("attach-comp").select_option(str(setup["competition"]["id"]))
    page.get_by_test_id("attach-member").select_option(str(member["id"]))
    if comment:
        page.get_by_test_id("attach-comment").fill(comment)
    page.get_by_test_id("attach-save").click()
    expect(toast(page)).to_contain_text("rattaché avec succès")


def test_sync_links_payment_automatically(mobile_page, test_data, setup):
    page = open_screen(mobile_page)
    _sync(page)
    expect(_item_card(page, setup["auto"]).get_by_test_id("ha-state")).to_contain_text("Rattaché")
    expect(_item_card(page, setup["unknown_payer"]).get_by_test_id("ha-state")).to_contain_text("En attente")
    expect(_item_card(page, setup["no_competition"]).get_by_test_id("ha-state")).to_contain_text("En attente")

    go_to(page, "competitions")
    open_competition(page, setup["competition"]["nom"])
    expect(participant_card(page, setup["members"][0]).get_by_test_id("payment-badge")).to_contain_text("Payé")

    def linked():
        assert test_data.helloasso_item(setup["auto"]["id"])["source"] == "auto"
    eventually(linked)


def test_manual_link_marks_member_paid(mobile_page, test_data, setup):
    member = setup["members"][1]
    page = open_screen(mobile_page)
    _sync(page)
    _item_card(page, setup["unknown_payer"]).get_by_test_id("ha-open").click()
    # Suggested from the competition number the payer typed
    expect(page.get_by_test_id("attach-comp")).to_have_value(str(setup["competition"]["id"]))
    page.get_by_test_id("attach-member").select_option(str(member["id"]))
    page.get_by_test_id("attach-comment").fill("Paid by an uncle")
    page.get_by_test_id("attach-save").click()
    expect(toast(page)).to_contain_text("rattaché avec succès")
    card = _item_card(page, setup["unknown_payer"])
    expect(card.get_by_test_id("ha-state")).to_contain_text("Rattaché")
    expect(card).to_contain_text("manuel")

    go_to(page, "competitions")
    open_competition(page, setup["competition"]["nom"])
    expect(participant_card(page, member).get_by_test_id("payment-badge")).to_contain_text("Payé")

    def stored():
        doc = test_data.helloasso_item(setup["unknown_payer"]["id"])
        assert (doc["competition_id"], doc["adherent_id"], doc["source"]) == (setup["competition"]["id"], member["id"], "manuel")
        participant = _participant(test_data, setup, member)
        assert (participant["montant_paye"], participant["commande_helloasso"]) == (15, str(setup["unknown_payer"]["order"]["id"]))
    eventually(stored)


def test_ignore_and_restore_a_payment(mobile_page, test_data, setup):
    page = open_screen(mobile_page)
    _sync(page)
    card = _item_card(page, setup["no_competition"])
    card.get_by_test_id("ha-open").click()
    page.get_by_test_id("attach-ignore").click()
    expect(page.get_by_test_id("attach-error")).to_contain_text("Indiquez un commentaire")
    page.get_by_test_id("attach-comment").fill("Shop purchase, not a competition")
    page.get_by_test_id("attach-ignore").click()
    expect(toast(page)).to_contain_text("Ligne ignorée")

    # Hidden from « Tous » while « hide ignored » is ticked (default)
    expect(card).to_have_count(0)
    page.get_by_test_id("ha-filter-ignored").click()
    expect(card.get_by_test_id("ha-state")).to_contain_text("Ignoré")

    def ignored():
        doc = test_data.helloasso_item(setup["no_competition"]["id"])
        assert (doc["ignore"], doc["ignore_motif"]) == (True, "Shop purchase, not a competition")
    eventually(ignored)

    card.get_by_test_id("ha-open").click()
    expect(page.get_by_test_id("attach-ignored")).to_contain_text("Shop purchase, not a competition")
    page.get_by_test_id("attach-ignore").click()
    expect(toast(page)).to_contain_text("n'est plus ignorée")

    def restored():
        assert test_data.helloasso_item(setup["no_competition"]["id"])["ignore"] is False
    eventually(restored)


def test_linking_pass_goes_from_one_pending_payment_to_the_next(mobile_page, test_data, setup):
    """« Rattacher les paiements en attente »: the pending payments of the list shown, one after another, each decision
    saved at once, then a summary."""
    page = open_screen(mobile_page)
    _sync(page)
    page.get_by_test_id("ha-filter-all").click()
    page.get_by_test_id("ha-search").fill(setup["tag"])
    expect(page.get_by_test_id("ha-item")).to_have_count(2)  # the list reloaded after the sync
    page.get_by_test_id("ha-first").click()
    dialog = page.get_by_test_id("attach-dialog")
    expect(dialog).to_contain_text("1 / 2")
    page.get_by_test_id("attach-skip").click()
    expect(dialog).to_contain_text("2 / 2")
    page.get_by_test_id("attach-comment").fill("Not a competition")
    page.get_by_test_id("attach-ignore").click()
    expect(dialog).to_have_count(0)
    expect(toast(page)).to_contain_text("🚫 1 ignoré · ⏭ 1 passé")

    def one_ignored():
        docs = [test_data.helloasso_item(setup[key]["id"]) for key in ("unknown_payer", "no_competition")]
        assert sorted(bool(doc.get("ignore")) for doc in docs) == [False, True]
    eventually(one_ignored)


def test_competition_links_open_the_competition(page, setup):
    """Desktop table: the competition detected from what the payer typed, and the linked one, open that competition."""
    page = open_screen(page)
    _sync(page)
    nom = setup["competition"]["nom"]
    _item_card(page, setup["unknown_payer"]).get_by_test_id("ha-detected").click()
    expect(page.get_by_test_id("detail-name")).to_have_text(nom)

    go_to(page, "helloasso")
    _item_card(page, setup["auto"]).get_by_test_id("ha-linked-competition").click()
    expect(page.get_by_test_id("detail-name")).to_have_text(nom)


def test_resync_keeps_coach_decisions(mobile_page, test_data, setup):
    """A new sync rewrites HelloAsso's fields only: manual links and ignored lines survive."""
    member = setup["members"][1]
    page = open_screen(mobile_page)
    _sync(page)
    _link(page, setup, setup["unknown_payer"], member)
    _item_card(page, setup["no_competition"]).get_by_test_id("ha-open").click()
    page.get_by_test_id("attach-comment").fill("Duplicate")
    page.get_by_test_id("attach-ignore").click()
    expect(toast(page)).to_contain_text("Ligne ignorée")

    page.get_by_test_id("ha-sync").click()
    expect(toast(page)).to_contain_text("Synchro terminée", timeout=20_000)

    def kept():
        linked = test_data.helloasso_item(setup["unknown_payer"]["id"])
        assert (linked["source"], linked["adherent_id"]) == ("manuel", member["id"])
        assert test_data.helloasso_item(setup["no_competition"]["id"])["ignore"] is True
    eventually(kept)


def test_webhook_marks_member_paid(page, test_data, setup):
    """HelloAsso notifies an order: the server re-reads it from the API and links it."""
    order_id = setup["auto"]["order"]["id"]
    refused = page.request.post("/webhooks/helloasso?token=wrong", data={"eventType": "Order", "data": {"id": order_id}})
    assert refused.status == 401

    accepted = page.request.post(f"/webhooks/helloasso?token={helloasso.WEBHOOK_TOKEN}",
                                 data={"eventType": "Order", "data": {"id": order_id}})
    assert accepted.ok, accepted.text()
    assert accepted.json()["verified"] == "api"

    # Stored as the phone's sync stores it (whose display test_sync_links_payment_automatically checks)
    def linked():
        member = setup["members"][0]
        assert test_data.helloasso_item(setup["auto"]["id"])["adherent_id"] == member["id"]
        assert _participant(test_data, setup, member)["statut_paiement"] == "paye"
    eventually(linked)


def test_webhook_ignores_other_forms(page, fake_helloasso):
    shop = item("Neville", "Longbottom", 5, form_slug="boutique-e2e")
    fake_helloasso.set([shop])
    answer = page.request.post(f"/webhooks/helloasso?token={helloasso.WEBHOOK_TOKEN}",
                               data={"eventType": "Order", "data": {"id": shop["order"]["id"]}})
    assert answer.ok and answer.json()["status"] == "ignored"


def test_desktop_sync_filters_and_link(page, test_data, setup):
    member = setup["members"][1]
    open_screen(page, "admin", "/bureau/competitions")
    _sync(page)
    page.get_by_test_id("ha-search").fill(setup["tag"])
    items = page.get_by_test_id("ha-item")
    page.get_by_test_id("ha-filter-all").click()
    expect(items).to_have_count(2)
    page.get_by_test_id("ha-filter-linked").click()
    expect(items).to_have_count(0)
    page.get_by_test_id("ha-filter-unlinked").click()
    expect(items).to_have_count(2)

    _link(page, setup, setup["unknown_payer"], member)

    def paid():
        participant = _participant(test_data, setup, member)
        assert (participant["statut_paiement"], participant["montant_paye"]) == ("paye", 15)
        assert participant["commande_helloasso"] == str(setup["unknown_payer"]["order"]["id"])
    eventually(paid)
