"""
Member data comes from the public HelloAsso form and must be treated as hostile: the members map and the pivot
table of the Outils page (Vue app) must show it as text.
"""

import os
import unittest

_code_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_outils = os.path.join(_code_root, "frontend", "src", "pages", "outils")
_SINKS = ("innerHTML", "v-html", "insertAdjacentHTML", "setContent(")


class TestMembersMapShowsText(unittest.TestCase):

    def test_no_html_from_member_data(self):
        """The map's popups and filter are built as text: no HTML string reaches Leaflet or the DOM."""
        for name in ("MembersMap.vue", "membersMapView.ts"):
            with open(os.path.join(_outils, name), encoding="utf-8") as f:
                source = f.read()
            for sink in _SINKS:
                self.assertNotIn(sink, source, name)
        # The popup itself is checked by behaviour in frontend/src/pages/outils/membersMapView.test.ts



class TestPivotTableShowsText(unittest.TestCase):

    def test_no_html_from_member_data(self):
        """The pivot table renders the members through vue-pivottable (Vue text, no HTML string); our code adds none
        (PivotPane.test.ts renders a hostile name)."""
        for name in ("PivotPane.vue", "pivotLayout.ts"):
            with open(os.path.join(_outils, name), encoding="utf-8") as f:
                source = f.read()
            for sink in _SINKS:
                self.assertNotIn(sink, source, name)


if __name__ == "__main__":
    unittest.main()
