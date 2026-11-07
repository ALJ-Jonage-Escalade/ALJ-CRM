"""Routes of src/api/members/members.py and src/api/members/seasons.py over a temporary member database
(auth off, local server)."""

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.members.schemas import MemberList
from support.member_db import MemberDbTestCase

import server


class TestMemberRoutes(MemberDbTestCase):

    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {"ALJ_API_AUTH": "off"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(server.app)

    def test_seasons(self):
        r = self.client.get("/api/seasons")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"seasons": ["2026-2027", "2025-2026"], "active": "2026-2027"})

    def test_members_of_the_active_season_by_default(self):
        self.seed_planning("Loisir adultes", ["Loisir"], jour="Lundi", horaires="19h", type="Loisir")
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.seed("2", "Max", "PETIT", "Loisir", season="2025-2026")
        r = self.client.get("/api/members")
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertEqual(data["season"], "2026-2027")
        self.assertEqual([m["first_name"] for m in data["members"]], ["Léo"])
        leo = data["members"][0]
        self.assertEqual((leo["creneau_groupe"], leo["creneau_details"], leo["status_norm"]),
                         ("Loisir adultes", "Lundi 19h", "Validé"))
        self.assertTrue(leo["purchase_id"])
        self.assertEqual(data["creneaux"][0]["tarifs"], ["Loisir"])
        # The body is built by hand (json_with_etag): it must still match the declared contract, field for field
        self.assertEqual(MemberList.model_validate(data).model_dump(), data)

        again = self.client.get("/api/members", headers={"If-None-Match": r.headers["etag"]})
        self.assertEqual(again.status_code, 304)

        past = self.client.get("/api/members", params={"season": "2025-2026"}).json()
        self.assertEqual([m["first_name"] for m in past["members"]], ["Max"])

    def test_unknown_season(self):
        r = self.client.get("/api/members", params={"season": "1999-2000"})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["code"], "not_found")


class TestMemberRecordRoutes(MemberDbTestCase):
    """Member record of the Vue app (admin): edit, add, payment certificate."""

    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {"ALJ_API_AUTH": "off"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(server.app)
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.leo = self.client.get("/api/members").json()["members"][0]

    def update(self, fields):
        return self.client.post("/api/members/update", json={"purchase_id": self.leo["purchase_id"], "fields": fields})

    def test_update_writes_only_the_fields_sent(self):
        r = self.update({"phone": "06 11 22 33 44", "badge_rouge": "Oui"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"status": "success", "message": "Fiche adhérent mise à jour avec succès."})
        leo = self.client.get("/api/members").json()["members"][0]
        self.assertEqual((leo["phone"], leo["badge_rouge"], leo["tarif_name"], leo["status_norm"]), ("06 11 22 33 44", "Oui", "Loisir", "Validé"))

    def test_members_carry_the_key_they_hold(self):
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.seed("2", "Max", "PETIT", "Loisir")
        ids = {m["first_name"]: m["user_id"] for m in self.client.get("/api/members").json()["members"]}
        key = self.client.post("/api/keys", json={"code": "12"}).json()
        r = self.client.post(f"/api/keys/{key['id']}/assignments", json={"user_id": ids["Léo"], "given_on": "2026-09-12"})
        self.assertEqual(r.status_code, 200, r.text)
        members = {m["first_name"]: m for m in self.client.get("/api/members").json()["members"]}
        self.assertEqual(members["Léo"]["key"], {"id": key["id"], "code": "12", "given_on": "2026-09-12"})
        self.assertIsNone(members["Max"]["key"])
        self.assertNotIn("hid_proxkey", members["Léo"])

    def test_update_modifies_all_fields_including_identity(self):
        r = self.update({
            "last_name": "BERNARD",
            "first_name": "Léonard",
            "birth_date": "2011-06-15",
            "amount": 135.5,
            "photo_auth": "Non",
        })
        self.assertEqual(r.status_code, 200, r.text)
        updated = self.client.get("/api/members").json()["members"][0]
        self.assertEqual(updated["last_name"], "BERNARD")
        self.assertEqual(updated["first_name"], "Léonard")
        self.assertEqual(updated["birth_date"], "2011-06-15")
        self.assertEqual(updated["amount"], 135.5)
        self.assertEqual(updated["photo_auth"], "Non")

    def contacts(self):
        return self.client.get("/api/members").json()["members"][0]["emergency_contacts"]

    def test_update_saves_the_contact_list_in_order(self):
        sent = [{"name": "PIERRE", "phone": "0601020304"}, {"name": "MARIE", "phone": ""}, {"name": "", "phone": "0605060708"}]
        self.assertEqual(self.update({"emergency_contacts": sent}).status_code, 200)
        self.assertEqual(self.contacts(), [{"name": "Pierre", "phone": "06 01 02 03 04"}, {"name": "Marie", "phone": ""},
                                           {"name": "", "phone": "06 05 06 07 08"}])

    def test_update_flat_read_fields_match_the_list(self):
        self.update({"emergency_contacts": [{"name": "PIERRE", "phone": "0601020304"}, {"name": "MARIE", "phone": "0605060708"}, {"name": "ANNA", "phone": ""}]})
        leo = self.client.get("/api/members").json()["members"][0]
        self.assertEqual((leo["emergency1_name"], leo["emergency1_phone"], leo["emergency2_name"], leo["emergency2_phone"]),
                         ("Pierre", "06 01 02 03 04", "Marie", "06 05 06 07 08"))

    def test_update_without_the_list_changes_nothing(self):
        self.update({"emergency_contacts": [{"name": "PIERRE", "phone": ""}]})
        self.assertEqual(self.update({"phone": "0611223344"}).status_code, 200)
        self.assertEqual(self.contacts(), [{"name": "Pierre", "phone": ""}])

    def test_update_empty_list_removes_the_contacts(self):
        self.update({"emergency_contacts": [{"name": "PIERRE", "phone": ""}]})
        self.assertEqual(self.update({"emergency_contacts": []}).status_code, 200)
        self.assertEqual(self.contacts(), [])

    def test_update_drops_blank_rows(self):
        self.update({"emergency_contacts": [{"name": " ", "phone": ""}, {"name": "PIERRE", "phone": ""}]})
        self.assertEqual(self.contacts(), [{"name": "Pierre", "phone": ""}])

    def test_update_refuses_the_flat_fields(self):
        # A tab of the previous build gets a visible error, never a silent loss (plans/emergency-contacts.md, D9)
        self.assertEqual(self.update({"emergency1_name": "PIERRE"}).status_code, 422)
        created = self.client.post("/api/members/create", json={"fields": {
            "last_name": "DUPONT", "first_name": "Jean", "birth_date": "2010-02-01", "tarif_name": "Loisir", "emergency1_name": "PIERRE"}})
        self.assertEqual(created.status_code, 422)

    def test_create_saves_the_contact_list(self):
        response = self.client.post("/api/members/create", json={"fields": {
            "last_name": "AAA", "first_name": "Jean", "birth_date": "2010-02-01", "tarif_name": "Loisir",
            "emergency_contacts": [{"name": "A", "phone": "0601020301"}, {"name": "B", "phone": "0601020302"}, {"name": "C", "phone": "0601020303"}]}})
        self.assertEqual(response.status_code, 200, response.text)
        created = [m for m in self.client.get("/api/members").json()["members"] if m["last_name"] == "AAA"][0]
        self.assertEqual([c["name"] for c in created["emergency_contacts"]], ["A", "B", "C"])

    def test_update_refusals(self):
        bad_email = self.update({"email_primary": "pas-une-adresse"})
        self.assertEqual(bad_email.status_code, 422)
        self.assertEqual(bad_email.json()["detail"][0]["loc"][-1], "email_primary")
        self.assertEqual(self.update({"badge_rouge": "peut-être"}).status_code, 422)
        self.assertEqual(self.update({"inconnu": "x"}).status_code, 422)
        # The key is no longer a member field: Outils › Clés (plans/club-keys.md)
        self.assertEqual(self.update({"hid_proxkey": "Oui"}).status_code, 422)
        empty = self.update({})
        self.assertEqual((empty.status_code, empty.json()["message"]), (400, "Aucune modification à enregistrer."))
        no_id = self.client.post("/api/members/update", json={"fields": {"phone": "0600000000"}})
        self.assertEqual(no_id.status_code, 400)

    def test_create_validation(self):
        r = self.client.post("/api/members/create", json={"fields": {"last_name": "DUPONT", "first_name": "Jean", "tarif_name": "Loisir"}})
        self.assertEqual((r.status_code, r.json()["message"]), (400, "La date de naissance est obligatoire."))
        r = self.client.post("/api/members/create", json={"fields": {"last_name": "DUPONT", "first_name": "Jean", "birth_date": "01/02/2010",
                                                                    "tarif_name": "Loisir"}})
        self.assertEqual(r.status_code, 422)  # ISO dates only (the form's date field)

    def test_create_adds_the_member_to_the_season(self):
        r = self.client.post("/api/members/create", json={"season": "2026-2027", "fields": {
            "last_name": "DUPONT", "first_name": "Jean", "birth_date": "2010-02-01", "tarif_name": "Loisir", "amount": 120}})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["season"], "2026-2027")
        names = [m["last_name"] for m in self.client.get("/api/members").json()["members"]]
        self.assertIn("DUPONT", names)

    def test_attestation_reads_the_member_from_the_database(self):
        with patch("api.communications.attestations.render_attestation_pdf", return_value=b"%PDF-fake") as render:
            r = self.client.post("/api/attestations/preview", json={"purchase_id": self.leo["purchase_id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.content, b"%PDF-fake")
        self.assertEqual(r.headers["content-type"], "application/pdf")
        # Accented name: ASCII fallback and UTF-8 form (HTTP headers are Latin-1)
        self.assertIn('filename="Attestation_MARTIN_Leo', r.headers["content-disposition"])
        self.assertIn("filename*=UTF-8''Attestation_MARTIN_L%C3%A9o", r.headers["content-disposition"])
        render.assert_called_once()
        missing = self.client.post("/api/attestations/preview", json={"purchase_id": 999999})
        self.assertEqual((missing.status_code, missing.json()["code"]), (404, "not_found"))
