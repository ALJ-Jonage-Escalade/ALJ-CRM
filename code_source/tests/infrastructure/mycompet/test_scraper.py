import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ajuster le chemin d'import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src")))
from infrastructure.mycompet.scraper import scrape_competition_info_by_id
from services.errors import InvalidRequest, NotFound, StorageUnavailable

class TestMyCompetScraper(unittest.TestCase):

    def test_normalize_result_url(self):
        from infrastructure.mycompet.scraper import normalize_result_url
        self.assertEqual(normalize_result_url("13660"), "https://mycompet.ffme.fr/resultat/resultat_13660")
        self.assertEqual(normalize_result_url("resultat_13660"), "https://mycompet.ffme.fr/resultat/resultat_13660")
        self.assertEqual(
            normalize_result_url("https://mycompet.ffme.fr/resultat/resultat_13660"),
            "https://mycompet.ffme.fr/resultat/resultat_13660"
        )
        self.assertEqual(normalize_result_url(""), "")

    def test_parse_mycompet_results_html(self):
        from infrastructure.mycompet.scraper import parse_mycompet_results_html
        sample_html = """
        <div class="regroupement">
            <div class="regroupement-header">[U13]Femme</div>
            <div class="regroupement-table">
                <table>
                    <tr><th>Rang</th><th>Identité</th><th>Total</th><th>Points</th><th>Cl.</th></tr>
                    <tr>
                        <td>1</td>
                        <td><a href="palmares_111111.html"><strong>AUTRE Club</strong><br>CLUB VERTIGE</a></td>
                        <td>15</td><td>1000</td><td>1</td>
                    </tr>
                    <tr>
                        <td>9</td>
                        <td><a href="palmares_930654.html"><strong>BULAND Julia</strong><br>AMICALE LAIQUE DE JONAGE</a></td>
                        <td>11</td><td>666.26</td><td>9</td>
                    </tr>
                </table>
            </div>
        </div>
        <div class="regroupement">
            <div class="regroupement-header">[U15]Homme</div>
            <div class="regroupement-table">
                <table>
                    <tr>
                        <td>1</td>
                        <td><a href="palmares_970269.html"><strong>CHAZOT Tiago</strong><br>AMICALE LAIQUE DE JONAGE</a></td>
                        <td>14</td><td>3044.04</td><td>1</td>
                    </tr>
                </table>
            </div>
        </div>
        """
        results = parse_mycompet_results_html(sample_html, club_keyword="JONAGE")
        self.assertEqual(len(results), 2)

        buland = next(r for r in results if r["licence"] == "930654")
        self.assertEqual(buland["nom"], "BULAND")
        self.assertEqual(buland["prenom"], "Julia")
        self.assertEqual(buland["classement"], "9")
        self.assertEqual(buland["total_categorie"], 2)
        self.assertEqual(buland["categorie"], "U13Femme")

        chazot = next(r for r in results if r["licence"] == "970269")
        self.assertEqual(chazot["nom"], "CHAZOT")
        self.assertEqual(chazot["prenom"], "Tiago")
        self.assertEqual(chazot["classement"], "1")
        self.assertEqual(chazot["total_categorie"], 1)
        self.assertEqual(chazot["categorie"], "U15Homme")

    def test_scrape_competition_info_invalid_id(self):
        with self.assertRaises(InvalidRequest):
            scrape_competition_info_by_id("abc")
        with self.assertRaises(InvalidRequest):
            scrape_competition_info_by_id("")

    @patch("requests.Session")
    def test_scrape_competition_info_network_error(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        import requests
        mock_session.get.side_effect = requests.RequestException("Connexion impossible")

        with self.assertRaises(StorageUnavailable):
            scrape_competition_info_by_id("18896")

    @patch("requests.Session")
    def test_scrape_competition_info_not_found(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        # 1. get /action/competitions
        r_entry = MagicMock()
        r_entry.status_code = 200
        r_entry.text = "<body onload=\"Echo.Boot.boot('/app', '0', false);\">"
        mock_session.get.return_value = r_entry

        # 2. post init, cal, filter
        r_init = MagicMock(status_code=200, text="<smsg></smsg>")
        r_cal = MagicMock(status_code=200, text='<c i="C.1" t="RTF"><s>Grid</s><p n="toolTipText">CompetitionAdm.c.id.tt</p>')
        r_filter = MagicMock(status_code=200, text="<smsg><c>Aucun résultat</c></smsg>")
        mock_session.post.side_effect = [r_init, r_cal, r_filter]

        with self.assertRaises(NotFound):
            scrape_competition_info_by_id("99999")

    @patch("requests.Session")
    def test_scrape_competition_info_success(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        r_entry = MagicMock(status_code=200, text="<body onload=\"Echo.Boot.boot('/app', '0', false);\">")
        mock_session.get.return_value = r_entry

        r_init = MagicMock(status_code=200, text="<smsg></smsg>")
        r_cal = MagicMock(status_code=200, text='<c i="C.2348" t="RTF"><s>Grid</s><p n="toolTipText">CompetitionAdm.c.id.tt</p>')
        
        filter_xml = """<smsg>
            <p n="text">18896</p>
            <c i="C.10"><p n="text">Coupe régionale de bloc Cusset Vichy</p></c>
            <c i="C.99" t="B"><p n="text">DÉTAILS</p></c>
        </smsg>"""
        r_filter = MagicMock(status_code=200, text=filter_xml)

        detail_xml = """<smsg>
            <p n="text">Nom </p></c><c><s>publicItemValue</s><p n="text">Coupe régionale de bloc Cusset Vichy</p></c>
            <p n="text">Date de la compétition </p></c><c><s>publicItemValue</s><p n="text">07/11/2026</p></c>
            <p n="text">ville </p></c><c><s>publicItemValue</s><p n="text">CUSSET</p></c>
            <p n="text">Discipline </p></c><c><s>publicItemValue</s><p n="text">Bloc</p></c>
        </smsg>"""
        r_det = MagicMock(status_code=200, text=detail_xml)

        mock_session.post.side_effect = [r_init, r_cal, r_filter, r_det]

        info = scrape_competition_info_by_id("18896")
        self.assertEqual(info["id_ffme"], "18896")
        self.assertEqual(info["nom"], "Coupe régionale de bloc Cusset Vichy")
        self.assertEqual(info["date_competition"], "2026-11-07")
        self.assertEqual(info["date_fin"], "2026-11-07")
        self.assertEqual(info["lieu"], "CUSSET")
        self.assertEqual(info["type"], "Bloc")

    @patch("requests.Session")
    def test_scrape_competition_info_two_days(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        r_entry = MagicMock(status_code=200, text="<body onload=\"Echo.Boot.boot('/app', '0', false);\">")
        mock_session.get.return_value = r_entry

        r_init = MagicMock(status_code=200, text="<smsg></smsg>")
        r_cal = MagicMock(status_code=200, text='<c i="C.2348" t="RTF"><s>Grid</s><p n="toolTipText">CompetitionAdm.c.id.tt</p>')

        filter_xml = """<smsg>
            <p n="text">18849</p>
            <c i="C.10"><p n="text">Championnat départemental de bloc Dordogne et Gironde</p></c>
            <c i="C.99" t="B"><p n="text">DÉTAILS</p></c>
        </smsg>"""
        r_filter = MagicMock(status_code=200, text=filter_xml)

        detail_xml = """<smsg>
            <p n="text">Nom </p></c><c><s>publicItemValue</s><p n="text">Championnat départemental de bloc Dordogne et Gironde</p></c>
            <p n="text">Date de la compétition </p></c><c><s>publicItemValue</s><p n="text">31/10/2026-01/11/2026</p></c>
            <p n="text">ville </p></c><c><s>publicItemValue</s><p n="text">PAREMPUYRE</p></c>
            <p n="text">Discipline </p></c><c><s>publicItemValue</s><p n="text">Bloc</p></c>
        </smsg>"""
        r_det = MagicMock(status_code=200, text=detail_xml)

        mock_session.post.side_effect = [r_init, r_cal, r_filter, r_det]

        info = scrape_competition_info_by_id("18849")
        self.assertEqual(info["id_ffme"], "18849")
        self.assertEqual(info["nom"], "Championnat départemental de bloc Dordogne et Gironde")
        self.assertEqual(info["date_competition"], "2026-10-31")
        self.assertEqual(info["date_fin"], "2026-11-01")
        self.assertEqual(info["lieu"], "PAREMPUYRE")
        self.assertEqual(info["type"], "Bloc")

    def test_parse_dates_to_iso(self):
        from infrastructure.mycompet.scraper import _parse_dates_to_iso
        self.assertEqual(_parse_dates_to_iso("31/10/2026-01/11/2026"), ("2026-10-31", "2026-11-01"))
        self.assertEqual(_parse_dates_to_iso("31/10/2026 - 01/11/2026"), ("2026-10-31", "2026-11-01"))
        self.assertEqual(_parse_dates_to_iso("du 31/10/2026 au 01/11/2026"), ("2026-10-31", "2026-11-01"))
        self.assertEqual(_parse_dates_to_iso("31/10/2026 01/11/2026"), ("2026-10-31", "2026-11-01"))
        self.assertEqual(_parse_dates_to_iso("07/11/2026"), ("2026-11-07", "2026-11-07"))
        self.assertEqual(_parse_dates_to_iso(""), (None, None))
        self.assertEqual(_parse_dates_to_iso(None), (None, None))



if __name__ == "__main__":
    unittest.main()
