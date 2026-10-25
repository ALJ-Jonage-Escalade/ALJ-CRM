"""
Member data comes from the public HelloAsso form and must be treated as hostile:
the server-built HTML page (/pivot) must never let it end a <script> block or
inject markup, the portal must render it in an isolated iframe, and the members map
(Vue app) must show it as text.
"""

import json
import os
import re
import sys
import unittest
from unittest.mock import patch

_tests_dir = os.path.dirname(os.path.abspath(__file__))
_code_root = os.path.dirname(_tests_dir)
_src_dir = os.path.join(_code_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi.testclient import TestClient  # noqa: E402

from domain.utils import json_for_script  # noqa: E402


PAYLOAD = '</script><img src=x onerror="alert(1)"><!--'


class TestJsonForScript(unittest.TestCase):

    def test_round_trip(self):
        data = [{"name": PAYLOAD, "sep": "a\u2028b\u2029c", "amp": "R&D"}]
        self.assertEqual(json.loads(json_for_script(data)), data)

    def test_no_markup_characters(self):
        out = json_for_script({"x": PAYLOAD})
        for char in "<>&\u2028\u2029":
            self.assertNotIn(char, out)


class TestServerPagesEscapeMemberData(unittest.TestCase):

    def setUp(self):
        from server import app
        self.client = TestClient(app)

    def _assert_payload_contained(self, html: str):
        self.assertNotIn(PAYLOAD, html)
        # The payload never closes a script block early nor adds a tag anywhere in the page.
        self.assertNotIn("<img", html.lower())
        self.assertNotIn("</script><", html.lower())

    def test_pivot_data(self):
        row = {"status": PAYLOAD, "city": PAYLOAD, "already_member": 0,
               "season_name": "2026-2027", "tarif_name": PAYLOAD}
        with patch("infrastructure.sqlite.members.MemberRepository.load_direct_data", return_value=[row]):
            html = self.client.get("/pivot").text
        self._assert_payload_contained(html)
        self.assertIn("\\u003c/script\\u003e", html)


class TestToolsIframesIsolated(unittest.TestCase):

    def test_no_same_origin_sandbox(self):
        """The pivot table (Vue app, Outils page) runs in a frame that cannot reach the session or the API."""
        with open(os.path.join(_code_root, "frontend", "src", "pages", "OutilsPage.vue"), encoding="utf-8") as f:
            html = f.read()
        sandboxes = re.findall(r'sandbox="([^"]*)"', html)
        self.assertEqual(len(sandboxes), 1)
        for value in sandboxes:
            self.assertNotIn("allow-same-origin", value)


class TestMembersMapShowsText(unittest.TestCase):

    def test_no_html_from_member_data(self):
        """The map's popups and filter are built as text: no HTML string reaches Leaflet or the DOM."""
        outils = os.path.join(_code_root, "frontend", "src", "pages", "outils")
        for name in ("MembersMap.vue", "membersMapView.ts"):
            with open(os.path.join(outils, name), encoding="utf-8") as f:
                source = f.read()
            for sink in ("innerHTML", "v-html", "insertAdjacentHTML", "setContent("):
                self.assertNotIn(sink, source, name)
        with open(os.path.join(outils, "membersMapView.ts"), encoding="utf-8") as f:
            self.assertIn("bindPopup(() => popup(p))", f.read())


if __name__ == "__main__":
    unittest.main()
