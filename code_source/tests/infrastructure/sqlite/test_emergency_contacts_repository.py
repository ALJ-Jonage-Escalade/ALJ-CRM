"""Emergency contacts in the member database: import, replacement, reads (plans/emergency-contacts.md, D2, D4)."""

from support.member_db import MemberDbTestCase

from domain.members.emergency_contacts import HELLOASSO_CONTACT_FIELDS
from domain.members.view import competitor_contacts, member_row
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository

(FIRST_NAME_KEY, FIRST_PHONE_KEY), (SECOND_NAME_KEY, SECOND_PHONE_KEY) = HELLOASSO_CONTACT_FIELDS


class ContactsCase(MemberDbTestCase):

    def seed_leo(self, ref="1", **extra):
        self.seed(ref, "Léo", "MARTIN", "Loisir", **extra)
        return MemberRepository.list_member_rows("2026-2027")[0]["user_id"]

    def rows(self, user_id):
        conn = SqliteDatabase.get_connection()
        try:
            return [tuple(r) for r in conn.execute(
                "SELECT name, phone, position FROM emergency_contacts WHERE user_id = ? ORDER BY position", (user_id,)).fetchall()]
        finally:
            conn.close()

    def execute(self, sql, *params):
        conn = SqliteDatabase.get_connection()
        try:
            result = conn.execute(sql, params).fetchall()
            conn.commit()
            return result
        finally:
            conn.close()

    def replace(self, user_id, contacts):
        MemberRepository.update_member_fields(user_id=user_id, fields={"emergency_contacts": contacts})


class TestImport(ContactsCase):

    def test_new_member_gets_the_contacts_of_the_form_in_order(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111", SECOND_NAME_KEY: "PAUL", SECOND_PHONE_KEY: "0622222222"})
        self.assertEqual(self.rows(user_id), [("CLAIRE", "0611111111", 0), ("PAUL", "0622222222", 1)])

    def test_form_without_contact_adds_nothing(self):
        self.assertEqual(self.rows(self.seed_leo()), [])

    def test_returning_member_gets_a_new_number_after_the_others(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111"})
        self.seed_leo("2", **{FIRST_NAME_KEY: "PAUL", FIRST_PHONE_KEY: "0622222222"})
        self.assertEqual(self.rows(user_id), [("CLAIRE", "0611111111", 0), ("PAUL", "0622222222", 1)])

    def test_same_number_in_another_spelling_is_not_added_and_existing_row_is_unchanged(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111"})
        self.seed_leo("2", **{FIRST_NAME_KEY: "Claire Martin", FIRST_PHONE_KEY: "+33 6 11 11 11 11"})
        self.assertEqual(self.rows(user_id), [("CLAIRE", "0611111111", 0)])

    def test_second_contact_of_a_later_form_is_added(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111"})
        self.seed_leo("2", **{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111", SECOND_NAME_KEY: "PAUL", SECOND_PHONE_KEY: "0622222222"})
        self.assertEqual(self.rows(user_id), [("CLAIRE", "0611111111", 0), ("PAUL", "0622222222", 1)])

    def test_import_no_longer_writes_the_old_columns(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE", FIRST_PHONE_KEY: "0611111111"})
        ((name, phone),) = self.execute("SELECT emergency1_name, emergency1_phone FROM users WHERE id = ?", user_id)
        self.assertEqual((name, phone), (None, None))


class TestReplace(ContactsCase):

    def test_grow_past_two_then_reorder_then_shrink_to_empty(self):
        user_id = self.seed_leo()
        self.replace(user_id, [{"name": "A", "phone": "01"}, {"name": "B", "phone": "02"}, {"name": "C", "phone": "03"}])
        self.assertEqual(self.rows(user_id), [("A", "01", 0), ("B", "02", 1), ("C", "03", 2)])
        self.replace(user_id, [{"name": "C", "phone": "03"}, {"name": "A", "phone": "01"}])
        self.assertEqual(self.rows(user_id), [("C", "03", 0), ("A", "01", 1)])
        self.replace(user_id, [])
        self.assertEqual(self.rows(user_id), [])

    def test_blank_rows_are_dropped(self):
        user_id = self.seed_leo()
        self.replace(user_id, [{"name": " ", "phone": ""}, {"name": "A", "phone": ""}])
        self.assertEqual(self.rows(user_id), [("A", "", 0)])

    def test_other_fields_leave_the_contacts_alone(self):
        user_id = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE"})
        MemberRepository.update_member_fields(user_id=user_id, fields={"phone": "0600000000"})
        self.assertEqual(self.rows(user_id), [("CLAIRE", "", 0)])

    def test_unchanged_rows_are_not_rewritten(self):
        user_id = self.seed_leo()
        self.replace(user_id, [{"name": "A", "phone": "01"}, {"name": "B", "phone": "02"}])
        self.execute("UPDATE emergency_contacts SET updated_at = 'avant'")
        self.replace(user_id, [{"name": "A", "phone": "01"}, {"name": "B2", "phone": "02"}])
        stamps = [r[0] for r in self.execute("SELECT updated_at FROM emergency_contacts ORDER BY position")]
        self.assertEqual(stamps[0], "avant")
        self.assertNotEqual(stamps[1], "avant")

    def test_contacts_of_another_member_are_untouched(self):
        leo = self.seed_leo(**{FIRST_NAME_KEY: "CLAIRE"})
        self.seed("2", "Zoé", "DURAND", "Loisir", **{FIRST_NAME_KEY: "ANNA"})
        zoe = [r["user_id"] for r in MemberRepository.list_member_rows("2026-2027") if r["first_name"] == "Zoé"][0]
        self.replace(leo, [])
        self.assertEqual(self.rows(zoe), [("ANNA", "", 0)])

    def test_manual_member_keeps_every_contact(self):
        MemberRepository.add_manual_member({
            "last_name": "VALENTIN", "first_name": "Claire", "birth_date": "2010-05-14", "tarif_name": "Loisir",
            "emergency_contacts": [{"name": "A", "phone": "01"}, {"name": "B", "phone": "02"}, {"name": "C", "phone": "03"}],
        }, "2026-2027")
        user_id = MemberRepository.list_member_rows("2026-2027")[0]["user_id"]
        self.assertEqual(self.rows(user_id), [("A", "01", 0), ("B", "02", 1), ("C", "03", 2)])


class TestReads(ContactsCase):

    def test_member_rows_carry_the_contacts_in_order(self):
        user_id = self.seed_leo()
        self.seed("2", "Zoé", "DURAND", "Loisir")
        self.replace(user_id, [{"name": "A", "phone": "01"}, {"name": "B", "phone": "02"}, {"name": "C", "phone": "03"}])
        self.execute("UPDATE emergency_contacts SET position = 2 - position")  # stored order is not the wanted order
        by_name = {r["first_name"]: r for r in MemberRepository.list_member_rows("2026-2027")}
        self.assertEqual(by_name["Léo"]["emergency_contacts"], [{"name": "C", "phone": "03"}, {"name": "B", "phone": "02"}, {"name": "A", "phone": "01"}])
        self.assertEqual(by_name["Zoé"]["emergency_contacts"], [])
        self.assertEqual([r["emergency_contacts"] for r in MemberRepository.list_member_rows_of_users([user_id])],
                         [by_name["Léo"]["emergency_contacts"]])

    def test_legacy_view_exposes_the_first_contact_by_position(self):
        user_id = self.seed_leo()
        self.replace(user_id, [{"name": "A", "phone": "01"}, {"name": "B", "phone": "02"}])
        self.execute("UPDATE emergency_contacts SET position = 1 - position")
        (row,) = MemberRepository.list_flat_member_rows("2026-2027")
        self.assertEqual((row["emergency1_name"], row["emergency1_phone"]), ("B", "02"))
        self.assertNotIn("emergency2_name", row)

    def test_legacy_view_without_contact_is_blank(self):
        self.seed_leo()
        (row,) = MemberRepository.list_flat_member_rows("2026-2027")
        self.assertEqual((row["emergency1_name"], row["emergency1_phone"]), ("", ""))


class TestView(ContactsCase):

    ROW = {"emergency_contacts": [{"name": "CLAIRE MARTIN", "phone": "+33611111111"}, {"name": "paul", "phone": ""}, {"name": "ANNA", "phone": "0633333333"}]}

    def test_contacts_are_formatted(self):
        member = member_row(self.ROW, {}, _ref_date())
        self.assertEqual(member["emergency_contacts"], [{"name": "Claire Martin", "phone": "06 11 11 11 11"}, {"name": "Paul", "phone": ""},
                                                        {"name": "Anna", "phone": "06 33 33 33 33"}])

    def test_flat_fields_come_from_the_first_two_contacts(self):
        member = member_row(self.ROW, {}, _ref_date())
        self.assertEqual((member["emergency1_name"], member["emergency1_phone"], member["emergency2_name"], member["emergency2_phone"]),
                         ("Claire Martin", "06 11 11 11 11", "Paul", ""))

    def test_flat_fields_are_blank_without_contact(self):
        member = member_row({}, {}, _ref_date())
        self.assertEqual(member["emergency_contacts"], [])
        self.assertEqual((member["emergency1_name"], member["emergency2_phone"]), ("", ""))

    def test_competitor_contacts_keep_the_flat_fields_for_tabs_of_the_old_build(self):
        (contact,) = competitor_contacts([{**self.ROW, "user_id": 7, "season_name": "2026-2027"}], [], "2026-2027")
        self.assertEqual((contact["adherent_id"], contact["emergency2_name"]), (7, "Paul"))


def _ref_date():
    import datetime
    return datetime.date(2026, 9, 1)
