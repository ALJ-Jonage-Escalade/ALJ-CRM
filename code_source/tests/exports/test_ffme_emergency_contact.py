"""FFME export: the person to warn is the member's first emergency contact (plans/emergency-contacts.md, D7)."""

import csv
import io
import os

from support.member_db import MemberDbTestCase

from exports.membership_excel import generate_ffme_csv
from infrastructure.sqlite.members import MemberRepository


class TestFfmeEmergencyContact(MemberDbTestCase):

    def export_line(self):
        out = os.path.join(self._tmp.name, "ffme.csv")
        generate_ffme_csv(MemberRepository.list_flat_member_rows("2026-2027"), output_path=out)
        with open(out, encoding="utf-8", newline="") as exported:
            (line,) = list(csv.DictReader(io.StringIO(exported.read()), delimiter=";"))
        return line

    def seed_member(self):
        self.seed("1", "Léo", "MARTIN", "Loisir", **{"champ_Adresse : numéro et nom de rue": "1 rue A", "champ_Code postal": "69330",
                                                     "champ_Ville": "Jonage", "champ_Téléphone ": "0600000000",
                                                     "champ_Adresse mail pour la réception des informations du club": "leo@test.com"})
        return MemberRepository.list_member_rows("2026-2027")[0]["user_id"]

    def replace(self, user_id, contacts):
        MemberRepository.update_member_fields(user_id=user_id, fields={"emergency_contacts": contacts})

    def contact_columns(self, line):
        return [value for key, value in line.items() if key and ("pap" in key.lower() or "prévenir" in key.lower())]

    def test_first_contact_by_position_is_exported_after_a_reorder(self):
        user_id = self.seed_member()
        self.replace(user_id, [{"name": "Claire MARTIN", "phone": "0611111111"}, {"name": "Paul DURAND", "phone": "0622222222"}])
        self.assertIn("0611111111", self.contact_columns(self.export_line()))
        self.replace(user_id, [{"name": "Paul DURAND", "phone": "0622222222"}, {"name": "Claire MARTIN", "phone": "0611111111"}])
        columns = self.contact_columns(self.export_line())
        self.assertIn("0622222222", columns)
        self.assertNotIn("0611111111", columns)

    def test_member_without_contact_exports_blank_columns(self):
        self.seed_member()
        self.assertEqual(set(self.contact_columns(self.export_line())), {""})
