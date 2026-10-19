"""Desktop competition form: any number of coaches, ticked in a list (plan cleanup C2)."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from domain.competition_models import Competition  # noqa: E402
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo  # noqa: E402
from support.fake_firestore import FirestoreRepoTestCase  # noqa: E402

_app = QApplication.instance() or QApplication([])


class TestCoachList(FirestoreRepoTestCase):

    def setUp(self):
        super().setUp()
        for cid, nom in ((1, "Zoé"), (2, "Adrien"), (3, "Marc"), (4, "Lina")):
            Repo.save_coach(nom, coach_id=cid)
        from presentation.pages.competitions import CompetitionsPage
        with patch("PySide6.QtWidgets.QMessageBox.critical"), patch("PySide6.QtWidgets.QMessageBox.warning"):
            self.page = CompetitionsPage()
        self.addCleanup(self.page.deleteLater)

    def rows(self):
        lst = self.page.input_coaches
        return [(lst.item(i).text(), lst.item(i).checkState() == Qt.Checked) for i in range(lst.count())]

    def test_saved_coaches_first_in_order_then_others_by_name(self):
        self.page.current_competition = Competition(id=9, nom="Épreuve", coach_ids=[3, 1, 4])
        self.page._fill_form()
        self.assertEqual(self.rows(), [("Marc", True), ("Zoé", True), ("Lina", True), ("Adrien", False)])
        self.assertEqual(self.page._checked_coach_ids(), [3, 1, 4])

    def test_new_competition_has_no_coach_ticked(self):
        self.page.current_competition = None
        self.page._fill_form()
        self.assertEqual([checked for _, checked in self.rows()], [False] * 4)
        self.assertEqual(self.page._checked_coach_ids(), [])

    def test_coach_tab_reload_keeps_the_ticks(self):
        self.page.current_competition = Competition(id=9, nom="Épreuve", coach_ids=[2])
        self.page._fill_form()
        self.page.input_coaches.item(1).setCheckState(Qt.Checked)  # tick a second coach
        self.page.reload_coaches_list()
        self.assertEqual(len(self.page._checked_coach_ids()), 2)
        self.assertEqual(self.page._checked_coach_ids()[0], 2)


if __name__ == "__main__":
    unittest.main()
