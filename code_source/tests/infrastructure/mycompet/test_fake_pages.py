"""The fake MyCompet pages (tests/support/mycompet/): anonymized template, read by the real parsers."""

from __future__ import annotations

import datetime
import re

import lxml.html

from infrastructure.mycompet.scraper import parse_ffme_archive_entries, parse_mycompet_results_html
from support.mycompet.fake_identities import FAKE_CLUBS, FAKE_FIRST_NAMES, FAKE_LICENCE_PREFIX, FAKE_SURNAMES
from support.mycompet.render import TEMPLATE_PATH, render_archives, render_results, results_url


def _template() -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as template:
        return template.read()


def test_template_holds_only_invented_climbers() -> None:
    """GDPR: no real climber left from the saved page (names, clubs, licences, links)."""
    doc = lxml.html.fromstring(_template())
    names = [s.text_content().strip() for s in doc.xpath("//a[contains(@href, 'palmares')]//strong")]
    assert len(names) >= 10
    for name in names:
        surname, first_name = name.split(" ", 1)
        assert surname in FAKE_SURNAMES and first_name in FAKE_FIRST_NAMES, name
    clubs = {" ".join(br.tail.split()) for br in doc.xpath("//a[contains(@href, 'palmares')]//br") if br.tail}
    assert clubs <= set(FAKE_CLUBS)
    licences = re.findall(r"palmares_(\d+)", _template())
    assert licences and all(re.fullmatch(FAKE_LICENCE_PREFIX + r"\d{5}", lic) for lic in licences)
    assert not re.search(r"ffme\.fr|https?://|<script", _template(), re.IGNORECASE)


def test_rendered_results_are_parsed_with_the_club_athletes() -> None:
    page = render_results("Coupe du Rhône de bloc", "Jonage", [
        {"nom": "Zorbalt", "prenom": "Quessa", "licence": "9970001", "categorie": "U13 Femme", "classement": 2},
        {"nom": "Primskar", "prenom": "Taurin", "licence": "9970002", "categorie": "U15 Femme", "classement": 11},
    ])
    assert "COUPE DU RHÔNE DE BLOC - JONAGE" in page

    rows = {r["licence"]: r for r in parse_mycompet_results_html(page, club_keyword="JONAGE")}
    assert set(rows) == {"9970001", "9970002"}
    assert (rows["9970001"]["nom"], rows["9970001"]["prenom"], rows["9970001"]["classement"]) == ("ZORBALT", "Quessa", "2")
    assert rows["9970001"]["categorie"] == "U13Femme"
    # Past the template's last row: rows are added, so the rank and the category size follow
    assert (rows["9970002"]["classement"], rows["9970002"]["total_categorie"]) == ("11", 11)


def test_rendered_archive_lines_are_parsed() -> None:
    page = render_archives([
        {"number": 99001, "title": "Coupe départementale de bloc Coupe du Rhône", "date": datetime.date(2026, 9, 26),
         "venue": "Jonage"},
    ])
    [entry] = parse_ffme_archive_entries(page)
    assert entry["url"] == results_url(99001)
    assert entry["title"] == "Coupe départementale de bloc Coupe du Rhône"
    assert entry["date"] == datetime.date(2026, 9, 26)
    assert entry["venue"] == "Jonage"
