"""SqliteRepository.list_member_rows / list_seasons (member list of the web pages)."""

from support.member_db import MemberDbTestCase

from infrastructure.sqlite_repository import SqliteRepository


class TestMemberRows(MemberDbTestCase):

    def test_rows_of_one_season_with_purchase_id(self):
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.seed("2", "Zoé", "DURAND", "Adultes")
        self.seed("3", "Max", "PETIT", "Loisir", season="2025-2026")
        rows = SqliteRepository.list_member_rows("2026-2027")
        self.assertEqual(sorted(r["first_name"] for r in rows), ["Léo", "Zoé"])
        self.assertTrue(all(r["purchase_id"] for r in rows))
        self.assertEqual({r["season_name"] for r in rows}, {"2026-2027"})

    def test_rows_of_users_every_season(self):
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.seed("2", "Zoé", "DURAND", "Adultes")
        self.seed("3", "Max", "PETIT", "Loisir", season="2025-2026")
        ids = {r["first_name"]: r["user_id"] for r in SqliteRepository.list_member_rows("2026-2027")}
        (max_id,) = [r["user_id"] for r in SqliteRepository.list_member_rows("2025-2026")]
        rows = SqliteRepository.list_member_rows_of_users([ids["Léo"], max_id])
        self.assertEqual(sorted((r["first_name"], r["season_name"]) for r in rows),
                         [("Léo", "2026-2027"), ("Max", "2025-2026")])
        self.assertEqual(SqliteRepository.list_member_rows_of_users([]), [])

    def test_same_people_as_the_legacy_view(self):
        self.seed("1", "Léo", "MARTIN", "Loisir")
        self.seed("2", "Zoé", "DURAND", "Adultes")
        legacy = SqliteRepository.load_direct_data("2026-2027")
        rows = SqliteRepository.list_member_rows("2026-2027")
        key = ("user_id", "last_name", "first_name", "tarif_name", "status", "order_ref", "season_name")
        self.assertEqual(sorted(tuple(r[k] for k in key) for r in rows),
                         sorted(tuple(r[k] for k in key) for r in legacy))

    def test_seasons(self):
        seasons = SqliteRepository.list_seasons()
        self.assertEqual([s["name"] for s in seasons], ["2026-2027", "2025-2026"])
        self.assertEqual([s["is_active"] for s in seasons], [True, False])
