"""Training slots (planning table): full replacement, one-slot saves, deletion, aggregation by group."""

from support.member_db import MemberDbTestCase

from infrastructure.sqlite.planning import PlanningRepository

SLOT = {"id": 1, "groupe": "U12", "type": "cours", "jour": "Mardi", "horaires": "18h-19h30",
        "encadrants": ["Léa"], "helloasso_tarifs": ["Loisir U12"], "naissance_min": 2014, "seance_autonome": 0}


class PlanningRepositoryTest(MemberDbTestCase):

    def test_save_planning_data_replaces_the_whole_planning(self):
        PlanningRepository.save_planning_data([dict(SLOT, groupe="Ancien")])
        PlanningRepository.save_planning_data([SLOT, {"id": 2, "groupe": "Adultes", "seance_autonome": 1}])
        first, second = PlanningRepository.load_planning_data()
        self.assertEqual((first["groupe"], first["encadrants"], first["helloasso_tarifs"]), ("U12", ["Léa"], ["Loisir U12"]))
        self.assertEqual((first["naissance_min"], first["seance_autonome"]), ("2014", False))
        self.assertEqual((second["groupe"], second["jour"], second["encadrants"], second["seance_autonome"]),
                         ("Adultes", "Lundi", [], True))

    def test_new_slot_gets_the_next_id_and_trimmed_values(self):
        PlanningRepository.save_planning_data([SLOT])
        saved = PlanningRepository.save_planning_item({"id": 0, "groupe": " U14 ", "horaires": " 17h "})
        self.assertEqual(saved["id"], 2)
        slot = PlanningRepository.load_planning_data()[1]
        self.assertEqual((slot["id"], slot["groupe"], slot["horaires"], slot["type"]), (2, "U14", "17h", "cours"))

    def test_saving_an_existing_slot_updates_it(self):
        PlanningRepository.save_planning_data([SLOT])
        PlanningRepository.save_planning_item(dict(SLOT, horaires="19h-20h30"))
        self.assertEqual([slot["horaires"] for slot in PlanningRepository.load_planning_data()], ["19h-20h30"])

    def test_delete_planning_item_says_whether_a_slot_was_removed(self):
        PlanningRepository.save_planning_data([SLOT])
        self.assertTrue(PlanningRepository.delete_planning_item(1))
        self.assertFalse(PlanningRepository.delete_planning_item(1))
        self.assertEqual(PlanningRepository.load_planning_data(), [])

    def test_groups_merge_their_slots_and_tarifs_sorted_by_name(self):
        PlanningRepository.save_planning_data([
            dict(SLOT, id=1, groupe="U12", helloasso_tarifs=["Loisir U12", " "]),
            dict(SLOT, id=2, groupe="Adultes", type="Autonome", helloasso_tarifs=[]),
            dict(SLOT, id=3, groupe="U12", jour="Jeudi", helloasso_tarifs=["Loisir U12", "Compétition U12"], seance_autonome=1),
            dict(SLOT, id=4, groupe=" "),
        ])
        adults, u12 = PlanningRepository.load_creneaux_groups()
        self.assertEqual((adults["groupe"], adults["type_autonome"], adults["seance_autonome"]), ("Adultes", True, False))
        self.assertEqual(u12["tarifs"], ["Loisir U12", "Compétition U12"])
        self.assertEqual(u12["slots"], [("Mardi", "18h-19h30"), ("Jeudi", "18h-19h30")])
        self.assertTrue(u12["seance_autonome"])
        self.assertFalse(u12["type_autonome"])
