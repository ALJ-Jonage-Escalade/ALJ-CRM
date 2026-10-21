"""GET /api/members/competitors: contacts of the competitors, kept offline by the phone
(plan phase 5). In-memory Firestore for the competitions, temporary member database."""

from support.api_case import ApiTestCase
from support.member_db import MemberDbTestCase

from domain.members.view import COMPETITOR_FIELDS
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from infrastructure.sqlite.members import MemberRepository

EMERGENCY = {
    "champ_Téléphone ": "+33612345678",
    "champ_Personne à prévenir en cas d'urgence - NOM  et PRENOM en majuscule": "CLAIRE MARTIN",
    "champ_Personne à prévenir en cas d'urgence - Téléphone": "0611111111",
    "champ_Parent 2  à prévenir en cas d'urgence - NOM ET PRENOM (en majuscule)": "PAUL MARTIN",
    "champ_Parent 2 - Numéro de téléphone portable": "0622222222",
}


class TestCompetitors(MemberDbTestCase, ApiTestCase):

    def setUp(self):
        super().setUp()
        self.seed_planning("Compétition U18", ["Compétition U18"])
        self.seed("1", "Léo", "MARTIN", "Compétition U18", **EMERGENCY)
        self.seed("2", "Max", "PETIT", "Compétition U18")
        self.seed("3", "Zoé", "DURAND", "Compétition U18")
        ids = {r["first_name"]: r["user_id"] for r in MemberRepository.list_member_rows("2026-2027")}
        self.leo, self.max, self.zoe = ids["Léo"], ids["Max"], ids["Zoé"]
        for aid in ids.values():
            self.seed_adherent(aid)

    def test_contacts_of_participants_of_open_competitions_only(self):
        open_comp = self.create()["id"]
        closed_comp = self.create(nom="Coupe passée", statut="close")["id"]
        Repo.add_participant(open_comp, self.leo)
        Repo.add_participant(open_comp, self.max, selectionne=False)
        Repo.add_participant(closed_comp, self.zoe)

        r = self.client.get("/api/members/competitors")
        self.assertEqual(r.status_code, 200, r.text)
        by_id = {c["adherent_id"]: c for c in r.json()}
        self.assertEqual(set(by_id), {self.leo, self.max})
        self.assertEqual(by_id[self.leo], {
            "adherent_id": self.leo, "last_name": "MARTIN", "first_name": "Léo",
            "phone": "06 12 34 56 78", "creneau_groupe": "Compétition U18",
            "emergency1_name": "Claire Martin", "emergency1_phone": "06 11 11 11 11",
            "emergency2_name": "Paul Martin", "emergency2_phone": "06 22 22 22 22",
        })

        again = self.client.get("/api/members/competitors", headers={"If-None-Match": r.headers["etag"]})
        self.assertEqual(again.status_code, 304)

    def test_only_the_agreed_fields(self):
        """No health, address or e-mail data leaves the server for the phone (plan O2)."""
        Repo.add_participant(self.create()["id"], self.leo)
        (contact,) = self.client.get("/api/members/competitors").json()
        self.assertEqual(set(contact), {"adherent_id", *COMPETITOR_FIELDS})
        for field in ("health_commitment", "document_sante", "address", "email_primary", "birth_date"):
            self.assertNotIn(field, contact)

    def test_participant_not_registered_again_keeps_last_season_contacts(self):
        self.seed("9", "Inès", "ROUX", "Compétition U18", season="2025-2026", **EMERGENCY)
        (ines,) = [r["user_id"] for r in MemberRepository.list_member_rows("2025-2026")]
        Repo.add_participant(self.create()["id"], ines)
        (contact,) = self.client.get("/api/members/competitors").json()
        self.assertEqual((contact["adherent_id"], contact["first_name"], contact["emergency2_phone"]),
                         (ines, "Inès", "06 22 22 22 22"))

    def test_active_season_row_preferred(self):
        self.seed("10", "Léo", "MARTIN", "Ancien tarif", season="2025-2026", **EMERGENCY)
        rows = MemberRepository.list_member_rows_of_users([self.leo])
        self.assertEqual({r["season_name"] for r in rows}, {"2025-2026", "2026-2027"})
        Repo.add_participant(self.create()["id"], self.leo)
        (contact,) = self.client.get("/api/members/competitors").json()
        self.assertEqual(contact["creneau_groupe"], "Compétition U18")

    def test_no_competition(self):
        self.assertEqual(self.client.get("/api/members/competitors").json(), [])
