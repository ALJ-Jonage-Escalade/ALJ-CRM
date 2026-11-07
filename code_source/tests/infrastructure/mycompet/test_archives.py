"""Results URL search in the FFME archive: name and venue matching, date check (plan b2), no network."""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.mycompet import scraper
from infrastructure.mycompet.scraper import find_mycompet_result_url, find_result_url_in_archives, parse_ffme_archive_entries
from support.mycompet.render import render_archives, results_url

# Same venue on two weekends: the earlier one is the decoy a loose match would pick
ARCHIVE = parse_ffme_archive_entries(render_archives([
    {"number": 99010, "title": "Coupe départementale de bloc du Pays Imaginaire", "date": datetime.date(2026, 9, 12),
     "venue": "Valbrume"},
    {"number": 99011, "title": "Open régional de bloc de Valbrume", "date": datetime.date(2026, 10, 17), "venue": "Valbrume"},
    {"number": 99012, "title": "Coupe régionale de difficulté Brumevent", "date": datetime.date(2026, 10, 3),
     "venue": "Pontgris"},
]))


@pytest.mark.parametrize(("nom", "lieu", "debut", "fin", "expected"), [
    ("Open régional Valbrume", "Valbrume", "2026-10-17", "", 99011),       # name and date
    ("Open régional Valbrume", "Valbrume", "2026-10-16", "", 99011),       # ± 1 day
    ("Championnat du club", "Valbrume", "2026-09-12", "", 99010),          # venue only, right date
    ("Coupe Brumevent", "", "2026-10-02", "2026-10-04", 99012),            # within a multi-day event
])
def test_dated_line_is_accepted(nom: str, lieu: str, debut: str, fin: str, expected: int) -> None:
    assert find_result_url_in_archives(ARCHIVE, nom, lieu, debut, fin, require_date=True) == results_url(expected)


@pytest.mark.parametrize(("nom", "lieu", "debut"), [
    ("Open régional Valbrume", "Valbrume", "2026-11-28"),   # same name and venue, another date: decoy
    ("Open régional Valbrume", "Valbrume", ""),             # no date to check
    ("Coupe de Nullepart", "Ailleurs", "2026-10-17"),       # nothing matches
])
def test_undated_line_is_refused_when_the_date_is_required(nom: str, lieu: str, debut: str) -> None:
    assert find_result_url_in_archives(ARCHIVE, nom, lieu, debut, require_date=True) == ""


def test_manual_search_falls_back_to_the_loose_match() -> None:
    """The per-competition fetch (a coach checks the page) still gets a name match without the date."""
    assert find_result_url_in_archives(ARCHIVE, "Coupe Brumevent", "Pontgris", "2027-01-15") == results_url(99012)
    assert find_result_url_in_archives(ARCHIVE, "Championnat", "Pontgris") == results_url(99012)


def test_find_mycompet_result_url_reads_the_archive_once() -> None:
    response = MagicMock(status_code=200, text=render_archives([
        {"number": 99020, "title": "Open de bloc Valbrume", "date": datetime.date(2026, 10, 17), "venue": "Valbrume"}]))
    with patch.object(scraper.requests, "get", return_value=response) as get:
        assert find_mycompet_result_url("Open Valbrume", "2026-10-17", "Valbrume") == results_url(99020)
    get.assert_called_once()
    assert get.call_args.args[0] == "https://www.ffme.fr/escalade/competition/archives-resultats-escalade/"


@pytest.mark.parametrize("failure", [requests.ConnectionError("down"), MagicMock(status_code=503, text="")])
def test_find_mycompet_result_url_without_archive(failure) -> None:
    kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
    with patch.object(scraper.requests, "get", **kwargs):
        assert find_mycompet_result_url("Open Valbrume", "2026-10-17", "Valbrume") == ""


def test_dev_override_of_the_mycompet_and_archive_urls(monkeypatch) -> None:
    """MYCOMPET_BASE_URL / FFME_ARCHIVES_URL point to the local fake in dev mode only."""
    monkeypatch.setenv("MYCOMPET_BASE_URL", "http://localhost:8096")
    monkeypatch.setenv("FFME_ARCHIVES_URL", "http://localhost:8096/archives")
    assert scraper._fetch_url(results_url(99030)) == results_url(99030)  # production mode: ignored
    assert scraper.runtime_env.ffme_archives_url().startswith("https://www.ffme.fr/")
    monkeypatch.setenv("ALJ_ENV", "dev")
    assert scraper._fetch_url(results_url(99030)) == "http://localhost:8096/resultat/resultat_99030"
    assert scraper.runtime_env.ffme_archives_url() == "http://localhost:8096/archives"
