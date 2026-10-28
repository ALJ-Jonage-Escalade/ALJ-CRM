"""Routes of src/api/ffme/ffme.py over a temporary member database (auth off, local server):
export statistics and CSV, then preview and import of the MyFFME licensee list."""

import base64
import io
import os
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

from infrastructure.security.api_auth import Role, required_role
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.ffme_import import UNREADABLE_EXCEL
from support.member_db import MemberDbTestCase

import server


def _xlsx(rows):
    """A MyFFME export: a title row, then the header (the importer finds it on the second row)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Liste des licenciés"])
    header = ["Nom", "Prénom", "N° de licence", "Date de naissance", "Passeports", "Diplômes", "Document de santé"]
    ws.append(header)
    for row in rows:
        ws.append([row.get(h, "") for h in header])
    buffer = io.BytesIO()
    wb.save(buffer)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestFfmeRoutes(MemberDbTestCase):

    def setUp(self):
        super().setUp()
        env = patch.dict(os.environ, {"ALJ_API_AUTH": "off"})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(server.app)

    def _user(self, last_name):
        conn = SqliteDatabase.get_connection()
        try:
            return dict(conn.execute("SELECT * FROM users WHERE last_name = ?", (last_name,)).fetchone())
        finally:
            conn.close()

    def _statuses(self, last_name):
        conn = SqliteDatabase.get_connection()
        try:
            rows = conn.execute("SELECT p.status_normalized, p.document_sante FROM purchases p JOIN users u ON u.id = p.user_id"
                                " WHERE u.last_name = ?", (last_name,)).fetchall()
            return [tuple(r) for r in rows]
        finally:
            conn.close()

    def test_roles(self):
        self.assertEqual(required_role("POST", "/api/ffme/preview"), Role.ADMIN)
        self.assertEqual(required_role("POST", "/api/ffme/import"), Role.ADMIN)
        self.assertEqual(required_role("GET", "/api/ffme/export"), Role.COACH)
        self.assertEqual(required_role("GET", "/api/ffme/stats"), Role.COACH)

    def test_stats_and_csv_export(self):
        self.seed("1", "Léo", "MARTIN", "Adultes autonomes")
        self.seed("2", "Max", "PETIT", "Adultes autonomes", **{"champ_Date de naissance de l'adhérent": ""})
        stats = self.client.get("/api/ffme/stats", params={"season": "2026-2027"}).json()
        self.assertEqual((stats["status"], stats["season"]), ("success", "2026-2027"))
        self.assertEqual((stats["estimated_total"], stats["new_licences_count"], stats["renewals_count"]), (1, 1, 0))
        self.assertEqual(stats["ignored_details"], ["PETIT Max (date de naissance manquante/invalide)"])

        resp = self.client.get("/api/ffme/export", params={"season": "2026-2027", "include_termine": "true"})
        self.assertEqual(resp.headers["content-type"], "text/csv; charset=utf-8")
        self.assertRegex(resp.headers["content-disposition"], r'attachment; filename="import_ffme_\d{8}_\d{6}\.csv"')
        text = resp.content.decode("utf-8-sig")
        self.assertTrue(text.startswith("numero de licence;nom;prenom"))
        self.assertIn("MARTIN", text)
        self.assertNotIn("PETIT", text)

    def test_csv_export_member_without_sex(self):
        # A first licence needs the sex (never guessed): left out and reported; a renewal is sent with it empty
        self.seed("1", "Léo", "MARTIN", "Adultes autonomes", champ_Sexe="")
        self.seed("2", "Max", "PETIT", "Adultes autonomes", champ_Sexe="", **{"champ_Numéro de Licence FFME (6 chiffres)": "123456"})
        stats = self.client.get("/api/ffme/stats", params={"season": "2026-2027"}).json()
        self.assertEqual((stats["estimated_total"], stats["renewals_count"], stats["new_licences_count"]), (1, 1, 0))
        self.assertEqual(stats["ignored_details"], ["MARTIN Léo (sexe non renseigné)"])

        text = self.client.get("/api/ffme/export", params={"season": "2026-2027"}).content.decode("utf-8-sig")
        self.assertNotIn("MARTIN", text)
        petit = next(line for line in text.splitlines() if "PETIT" in line)
        self.assertEqual(petit.split(";")[:5], ["123456", "PETIT", "Max", "10/03/2017", ""])

    def test_csv_export_sex_code(self):
        self.seed("1", "Léa", "MARTIN", "Adultes autonomes", champ_Sexe="Féminin")
        text = self.client.get("/api/ffme/export", params={"season": "2026-2027"}).content.decode("utf-8-sig")
        martin = next(line for line in text.splitlines() if "MARTIN" in line)
        self.assertEqual(martin.split(";")[4], "F")

    def test_bad_season_refused(self):
        for path in ("/api/ffme/stats", "/api/ffme/export"):
            with self.subTest(path=path):
                r = self.client.get(path, params={"season": "../x"})
                self.assertEqual((r.status_code, r.json()["message"]), (400, "Saison invalide (format attendu : AAAA-AAAA)."))

    def test_preview_then_import_with_a_manual_match(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        self.seed("2", "Max", "PETIT", "Cours ados")
        content = _xlsx([
            {"Nom": "MARTIN", "Prénom": "Léo", "N° de licence": "112233", "Passeports": "Grimpeur Vert",
             "Diplômes": "Initiateur SAE", "Document de santé": "Questionnaire de santé"},
            {"Nom": "PETIT-DUPONT", "Prénom": "Maxime", "N° de licence": "998877", "Date de naissance": "22/07/2009",
             "Passeports": "Grimpeur Bleu", "Document de santé": "Certificat médical"},
        ])

        preview = self.client.post("/api/ffme/preview", json={"filename": "ffme.xlsx", "content_base64": content}).json()
        self.assertEqual((preview["matched_count"], preview["unmatched_count"]), (1, 1))
        self.assertEqual(preview["stats"], {"total_processed": 2, "matched_by_licence": 0, "matched_by_name": 1,
                                            "matched_manually": 0, "errors": []})
        self.assertEqual(preview["unmatched"], [{
            "nom": "PETIT-DUPONT", "prenom": "Maxime", "licence": "998877", "birth_date": "22/07/2009",
            "passeports": "Grimpeur Bleu", "diplomes": "", "document_sante": "Certificat médical"}])
        self.assertEqual(sorted(u["last_name"] for u in preview["users"]), ["MARTIN", "PETIT"])
        self.assertEqual(self._user("MARTIN")["licence_ffme"] or "", "")  # nothing written yet

        petit = self._user("PETIT")["id"]
        row = preview["unmatched"][0]
        manual = {"user_id": petit, **{k: row[k] for k in ("nom", "prenom", "licence", "passeports", "diplomes", "document_sante")}}
        result = self.client.post("/api/ffme/import", json={"filename": "ffme.xlsx", "content_base64": content,
                                                            "manual_matches": [manual]}).json()
        self.assertEqual((result["status"], result["updated_count"], result["matched_manually"]), ("success", 2, 1))
        self.assertEqual(result["message"], "Importation FFME validée : 2 adhérents mis à jour.")

        martin = self._user("MARTIN")
        self.assertEqual((martin["licence_ffme"], martin["raw_passports"], martin["raw_diplomas"]),
                         ("112233", "Grimpeur Vert", "Initiateur SAE"))
        self.assertEqual(self._statuses("MARTIN"), [("Terminé", "Questionnaire de santé")])
        self.assertEqual(self._user("PETIT")["licence_ffme"], "998877")
        self.assertEqual(self._statuses("PETIT"), [("Terminé", "Certificat médical")])

    def test_import_refusals(self):
        no_header = _xlsx([])
        wb = openpyxl.Workbook()
        wb.active.append(["Autre", "Chose"])
        buffer = io.BytesIO()
        wb.save(buffer)
        wrong_columns = base64.b64encode(buffer.getvalue()).decode("ascii")
        for path, body, message in (
            ("/api/ffme/preview", {"content_base64": ""}, "Fichier Excel manquant (content_base64 obligatoire)."),
            ("/api/ffme/preview", {"content_base64": "pas du base64 !"}, "Fichier illisible : il doit s'agir d'un fichier Excel encodé en base64."),
            ("/api/ffme/preview", {"content_base64": wrong_columns}, "Colonne requise manquante dans le fichier Excel : Nom"),
            # Valid base64, but not an Excel file: the reader's error stays in the logs
            ("/api/ffme/preview", {"content_base64": base64.b64encode(b"not a workbook").decode("ascii")}, UNREADABLE_EXCEL),
            ("/api/ffme/import", {"content_base64": no_header}, "Aucune mise à jour à appliquer (aucun rapprochement trouvé)."),
            ("/api/ffme/import", {"content_base64": wrong_columns}, "Colonne requise manquante dans le fichier Excel : Nom"),
            ("/api/ffme/import", {"season": "../x", "content_base64": no_header}, "Saison invalide (format attendu : AAAA-AAAA)."),
        ):
            with self.subTest(path=path, body=body):
                r = self.client.post(path, json=body)
                self.assertEqual((r.status_code, r.json()["message"]), (400, message))
        # The matches are computed by the server, never taken from the request
        r = self.client.post("/api/ffme/import", json={"content_base64": no_header, "updates": [["Terminé", "1", "", "", "", 1]]})
        self.assertEqual(r.status_code, 422)
