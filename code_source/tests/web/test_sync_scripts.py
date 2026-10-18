"""web/shared/alj-sync.js and alj-members-sync.js run in Node (sync_scripts_harness.js): answers
that arrive after a season switch or a stop must not reach the page. Skipped without Node."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from typing import Any, Dict

TESTS_WEB = os.path.dirname(os.path.abspath(__file__))
SHARED = os.path.join(os.path.dirname(os.path.dirname(TESTS_WEB)), "web", "shared")
NODE = shutil.which("node")


@unittest.skipIf(NODE is None, "Node.js not installed")
class TestSyncScripts(unittest.TestCase):

    results: Dict[str, Any] = {}

    @classmethod
    def setUpClass(cls) -> None:
        assert NODE is not None
        run = subprocess.run([NODE, os.path.join(TESTS_WEB, "sync_scripts_harness.js"), SHARED],
                             capture_output=True, text=True, timeout=60, check=False)
        if run.returncode != 0:
            raise AssertionError(f"harness failed:\n{run.stderr}")
        cls.results = json.loads(run.stdout)

    def scenario(self, name: str) -> Dict[str, Any]:
        result = self.results[name]
        self.assertNotIn("error", result, result.get("error"))
        return result

    def test_late_answer_of_previous_season_is_dropped(self) -> None:
        result = self.scenario("late_answer_of_previous_season")
        self.assertEqual(result["shown"], [{"season": "2025-2026", "members": ["DURAND"]}])
        self.assertEqual(result["last_request"], "/api/members?season=2025-2026")  # season not switched back

    def test_early_answer_of_previous_season_is_dropped(self) -> None:
        self.assertEqual(self.scenario("early_answer_of_previous_season")["shown"],
                         [{"season": "2025-2026", "members": ["DURAND"]}])

    def test_active_season_keeps_updating(self) -> None:
        self.assertEqual(self.scenario("active_season_keeps_updating")["shown"],
                         [{"season": "2026-2027", "members": ["MARTIN"]},
                          {"season": "2026-2027", "members": ["MARTIN", "PETIT"]}])

    def test_stopped_poll_drops_its_answer(self) -> None:
        self.assertEqual(self.scenario("stopped_poll_drops_its_answer")["calls"], [])
