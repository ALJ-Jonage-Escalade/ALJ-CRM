"""Fake MyCompet results pages and FFME archive pages, for the unit tests and e2e/fakes/mycompet_fake.py.

render_results() fills the anonymized template (results_template.html, made by dev/make_mycompet_fixture.py)
with the club athletes a test needs: they are injected at render time, so they can be any test data (the seed's
members come from Faker and change with it). render_archives() writes the FFME archive lines in the real format:
« <title> – dd/mm/yyyy – <a href=…resultat_N>venue</a> ».
"""
from __future__ import annotations

import copy
import datetime
import html
import os
import re
from typing import List, TypedDict

import lxml.html

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results_template.html")
CLUB_NAME = "AMICALE LAIQUE DE JONAGE"
# Stored results URLs keep the real address; in dev the scraper fetches them from MYCOMPET_BASE_URL
RESULTS_URL = "https://mycompet.ffme.fr/resultat/resultat_{number}"


class ClubAthlete(TypedDict):
    nom: str
    prenom: str
    licence: str
    categorie: str   # template category, e.g. "U13 Femme" (first category when unknown)
    classement: int  # row replaced in that category (1 = first); past the last row, rows are added


class ArchiveLine(TypedDict):
    number: int   # MyCompet results page number
    title: str
    date: datetime.date
    venue: str


def results_url(number: int) -> str:
    return RESULTS_URL.format(number=number)


def _category(group) -> str:
    header = group.xpath(".//div[contains(@class, 'regroupement-header')]")
    words = " ".join(t.strip() for t in (header[0].itertext() if header else []) if t.strip())
    return re.sub(r"[\[\]]", "", words).strip().lower()


def _rows(group) -> list:
    return group.xpath(".//tr[.//a[contains(@href, 'palmares')]]")


def _set_identity(row, athlete: ClubAthlete, club: str) -> None:
    link = row.xpath(".//a[contains(@href, 'palmares')]")[0]
    link.attrib["href"] = f"palmares_{athlete['licence']}.html"
    link.xpath(".//strong")[0].text = f"{athlete['nom'].upper()} {athlete['prenom']}"
    for br in link.xpath(".//br"):
        br.tail = club


def render_results(title: str, venue: str, club_athletes: List[ClubAthlete], club: str = CLUB_NAME) -> str:
    """A MyCompet results page: the template's invented climbers, with `club_athletes` at their rank."""
    with open(TEMPLATE_PATH, encoding="utf-8") as template:
        doc = lxml.html.fromstring(template.read())
    groups = doc.xpath("//div[contains(concat(' ', @class, ' '), ' regroupement ')]")
    for athlete in club_athletes:
        wanted = re.sub(r"[\[\]]", "", athlete["categorie"]).strip().lower()
        group = next((g for g in groups if _category(g) == wanted), groups[0])
        rows = _rows(group)
        while len(rows) < athlete["classement"]:
            extra = copy.deepcopy(rows[-1])
            rows[-1].addnext(extra)
            rank_cell = extra.xpath(".//td")[0]
            for span in rank_cell.xpath(".//span") or [rank_cell]:
                span.text = str(len(rows) + 1)
            rows = _rows(group)
        _set_identity(rows[athlete["classement"] - 1], athlete, club)
    page = lxml.html.tostring(doc, encoding="unicode", doctype="<!DOCTYPE html>")
    return page.replace("{{TITLE}}", html.escape(title.upper())).replace("{{VENUE}}", html.escape(venue.upper()))


def render_archives(lines: List[ArchiveLine]) -> str:
    """An FFME results archive page listing `lines`."""
    items = "\n".join(
        f"<li>{html.escape(line['title'])} – {line['date']:%d/%m/%Y} –"
        f"<a href=\"{results_url(line['number'])}\"> {html.escape(line['venue'])}</a></li>"
        for line in lines)
    return ("<!DOCTYPE html>\n<html><head><meta charset=\"UTF-8\"><title>Archives résultats escalade</title></head>\n"
            f"<body><div class=\"content\"><ul style=\"list-style-type: disc;\">\n{items}\n</ul></div></body></html>\n")
