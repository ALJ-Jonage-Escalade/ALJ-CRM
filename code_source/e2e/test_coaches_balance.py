"""Competitions screen, coaches and admins: the coaches (« Coachs ») and the competitors' season balance (« Bilan »)."""
import csv
import datetime
import io

from playwright.sync_api import expect

from helpers.competitions import SEEDED_COMPETITION, competition_card, go_to, open_screen, sub_menu_entry, toast
from helpers.data import eventually, unique_name
from helpers.dialogs import accept_dialogs


def _season() -> tuple[str, int]:
    """The current season (August to July) and the year its June falls in."""
    today = datetime.date.today()
    start = today.year if today.month >= 8 else today.year - 1
    return f"{start}-{start + 1}", start + 1


def _coach_card(page, nom):
    return page.get_by_test_id("coach-card").filter(has=page.get_by_test_id("coach-name").get_by_text(f"🏃 {nom}", exact=True))


def test_create_rename_delete_coach(mobile_page, test_data):
    page = open_screen(mobile_page)
    accept_dialogs(page)
    go_to(page, "coachs")
    nom = unique_name("E2E Coach")
    page.get_by_test_id("coach-new-name").fill(nom)
    page.get_by_test_id("coach-add").click()
    expect(toast(page)).to_contain_text("Coach ajouté")
    expect(_coach_card(page, nom)).to_be_visible()

    _coach_card(page, nom).get_by_test_id("coach-edit").click()
    expect(page.get_by_test_id("coach-edit-name")).to_have_value(nom)
    renamed = unique_name("E2E Coach renamed")
    page.get_by_test_id("coach-edit-name").fill(renamed)
    page.get_by_test_id("coach-save").click()
    expect(_coach_card(page, renamed)).to_be_visible()
    expect(_coach_card(page, nom)).to_have_count(0)

    _coach_card(page, renamed).get_by_test_id("coach-delete").click()
    expect(_coach_card(page, renamed)).to_have_count(0)

    def deleted():
        assert all(c["nom"] != renamed for c in test_data.coaches())
    eventually(deleted)


def test_coach_changes_reach_competitions(mobile_page, test_data):
    """A renamed coach shows under the new name on their competitions; a deleted one leaves them."""
    coach = unique_name("E2E Coach")
    coach_id = test_data.create_coach(coach)
    comp = unique_name("E2E Coached")
    test_data.create_competition(comp, date="2027-06-01", coach_ids=[coach_id])
    page = open_screen(mobile_page)
    accept_dialogs(page)
    expect(competition_card(page, comp)).to_contain_text(f"Coachs : {coach}")

    go_to(page, "coachs")
    expect(_coach_card(page, coach).get_by_test_id("coach-competitions")).to_contain_text(comp)
    _coach_card(page, coach).get_by_test_id("coach-edit").click()
    renamed = unique_name("E2E Coach renamed")
    page.get_by_test_id("coach-edit-name").fill(renamed)
    page.get_by_test_id("coach-save").click()
    expect(_coach_card(page, renamed)).to_be_visible()
    go_to(page, "competitions")
    expect(competition_card(page, comp)).to_contain_text(f"Coachs : {renamed}")

    go_to(page, "coachs")
    _coach_card(page, renamed).get_by_test_id("coach-delete").click()
    expect(_coach_card(page, renamed)).to_have_count(0)
    go_to(page, "competitions")
    expect(competition_card(page, comp)).to_contain_text("Aucun coach")

    def unassigned():
        assert test_data.competition_by_name(comp)["coach_ids"] == []
    eventually(unassigned)


def test_coach_opens_a_competition_they_follow(page):
    open_screen(page, "admin", "/bureau/competitions")
    go_to(page, "coachs")
    _coach_card(page, "Severus Snape").get_by_test_id("coach-competition").filter(has_text=SEEDED_COMPETITION).click()
    expect(page.get_by_test_id("detail-name")).to_have_text(SEEDED_COMPETITION)
    expect(sub_menu_entry(page, "competitions")).to_have_attribute("aria-current", "page")


def test_balance_of_an_athlete(mobile_page, test_data):
    member = test_data.members(competition_only=True)[4]
    season, june = _season()
    due, paid_comp = unique_name("E2E Due"), unique_name("E2E Paid")
    test_data.create_competition(due, date=f"{june}-06-03", prix=15, participants=[member["id"]], selected=[member["id"]])
    paid_id = test_data.create_competition(paid_comp, date=f"{june}-06-04", prix=10, participants=[member["id"]], selected=[member["id"]])
    test_data.mark_paid(paid_id, member["id"], 10.0)

    page = open_screen(mobile_page)
    go_to(page, "bilan")
    expect(page.get_by_test_id("balance-season")).to_have_value(season)
    page.get_by_test_id("balance-search").fill(f"{member['nom']} {member['prenom']}")
    card = page.get_by_test_id("balance-card").filter(has_text=member["prenom"])
    expect(card).to_have_count(1)
    expect(card.get_by_test_id("balance-lines")).to_contain_text(due)
    expect(card.get_by_test_id("balance-lines")).to_contain_text(paid_comp)
    # Other competitions of the seed can add to the totals: check only what this test adds up to
    expect(card.get_by_test_id("balance-state")).to_contain_text("Reste dû")


def test_season_balance_export(page, test_data, tmp_path):
    member = test_data.members(competition_only=True)[0]
    season, june = _season()
    nom = unique_name("E2E Bilan")
    test_data.create_competition(nom, date=f"{june}-05-27", prix=14, participants=[member["id"]], selected=[member["id"]])
    open_screen(page, "admin", "/bureau/competitions")
    go_to(page, "bilan")
    expect(page.get_by_test_id("balance-athletes")).not_to_have_text("0")
    card = page.get_by_test_id("balance-card").filter(has_text=member["prenom"]).first
    card.get_by_test_id("balance-toggle").click()
    # Desktop: the competitor's detail next to the list
    expect(card.get_by_test_id("balance-toggle")).to_have_attribute("aria-current", "true")
    expect(page.get_by_test_id("balance-detail")).to_contain_text(nom)

    with page.expect_download() as info:
        page.get_by_test_id("balance-export").click()
    target = tmp_path / info.value.suggested_filename
    info.value.save_as(target)
    rows = list(csv.reader(io.StringIO(target.read_text(encoding="utf-8-sig")), delimiter=";"))
    assert rows[0][0] == "Nom" and len(rows) > 1
    assert target.name == f"bilan_competitions_{season}.csv"
