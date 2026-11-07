"""`requests.get` stand-in serving the fake FFME archive and MyCompet pages: no test reaches the real sites.

Any other URL fails the test (AssertionError), so an unexpected call cannot go out unnoticed."""
from __future__ import annotations

import re
import unittest
from typing import Dict, List
from unittest.mock import MagicMock, patch

from infrastructure import runtime_env
from support.mycompet.render import ArchiveLine, ClubAthlete, render_archives, render_results


class MyCompetWebStub:
    def __init__(self) -> None:
        self.archive: List[ArchiveLine] = []
        self.pages: Dict[int, str] = {}          # results page number -> HTML
        self.failing: Dict[int, int] = {}        # results page number -> HTTP status
        self.requested: List[str] = []

    def add_competition(self, number: int, title: str, venue: str, date, club_athletes: List[ClubAthlete],
                        in_archive: bool = True) -> None:
        self.pages[number] = render_results(title, venue, club_athletes)
        if in_archive:
            self.archive.append(ArchiveLine(number=number, title=title, date=date, venue=venue))

    def get(self, url: str, *args, **kwargs) -> MagicMock:  # signature of requests.get
        self.requested.append(url)
        if url == runtime_env.ffme_archives_url():
            return MagicMock(status_code=200, text=render_archives(self.archive))
        found = re.fullmatch(re.escape(runtime_env.mycompet_base_url()) + r"/resultat/resultat_(\d+)", url)
        if found is None:
            raise AssertionError(f"Unexpected HTTP request in a test: {url}")
        number = int(found.group(1))
        if number in self.failing:
            return MagicMock(status_code=self.failing[number], text="")
        if number not in self.pages:
            return MagicMock(status_code=404, text="")
        return MagicMock(status_code=200, text=self.pages[number])

    def archive_requests(self) -> int:
        return self.requested.count(runtime_env.ffme_archives_url())


def use_mycompet_stub(test: unittest.TestCase) -> MyCompetWebStub:
    """Replace requests.get by the stub for the duration of `test`."""
    stub = MyCompetWebStub()
    patcher = patch("infrastructure.mycompet.scraper.requests.get", side_effect=stub.get)
    patcher.start()
    test.addCleanup(patcher.stop)
    return stub
