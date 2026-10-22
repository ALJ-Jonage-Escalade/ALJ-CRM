"""web/shared/alj-sync.js runs in Node (sync_scripts_harness.js): an answer that arrives after a stop
must not reach the page. Skipped without Node. (The season switch of the member list is tested with
the Vue app: frontend/src/composables/syncedResource.test.ts.)"""

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

    def test_stopped_poll_drops_its_answer(self) -> None:
        self.assertEqual(self.scenario("stopped_poll_drops_its_answer")["calls"], [])
