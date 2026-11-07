"""Daily MyCompet results batch, run from the Paramètres page by an admin, against the fake MyCompet and FFME
archive (e2e/fakes/mycompet_fake.py): rankings written to the competition, summary e-mail in Mailpit."""
import datetime

import pytest
from playwright.sync_api import expect

from helpers.data import eventually, unique_name

# The fake serves one state for the whole server
pytestmark = pytest.mark.xdist_group("mycompet")

RESULTS_TIMEOUT = 30_000  # the batch goes through every ended competition of the emulator (force=true)


def test_admin_runs_the_results_batch(page, login_as, test_data, fake_mycompet, mailpit):
    first, second = [m for m in test_data.members(competition_only=True) if m.get("num_licence")][:2]
    nom = unique_name("E2E Résultats")
    ended = datetime.date.today() - datetime.timedelta(days=3)
    competition_id = test_data.create_competition(nom, date=ended.isoformat(), participants=[first["id"], second["id"]],
                                                  selected=[first["id"], second["id"]])
    fake_mycompet.set([{
        "number": 99500, "title": nom, "venue": "Valbrume", "date": ended.isoformat(),
        "club_athletes": [{"nom": first["nom"], "prenom": first["prenom"], "licence": first["num_licence"],
                           "categorie": "U13 Femme", "classement": 2}],
    }])

    page.goto("/bureau/parametres")
    login_as(page, "admin")
    page.get_by_test_id("results-run").click()

    report = page.get_by_test_id("results-report")
    expect(report).to_contain_text(f"🏆 {nom} : 1 athlète(s) classé(s) pour le club", timeout=RESULTS_TIMEOUT)

    def ranked():
        participants = {p["adherent_id"]: p for p in test_data.competition(competition_id)["participants"]}
        assert participants[first["id"]]["classement"] == "2"
        assert not participants[second["id"]].get("classement")
        return test_data.competition(competition_id)
    assert eventually(ranked)["url_resultats"] == "https://mycompet.ffme.fr/resultat/resultat_99500"

    [mail] = mailpit.wait_for(f'subject:"{nom}"')
    assert first["nom"].upper() in mail["HTML"]
