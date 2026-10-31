"""Writes of the HelloAsso membership import (infrastructure/sqlite/membership_import.py) on a temporary member
database: schema, one transaction, every HelloAsso value kept (fake data only)."""

from __future__ import annotations

import datetime
import sqlite3
from dataclasses import replace
from typing import Any

from support.member_db import MemberDbTestCase

from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import Bucket, FieldChange, ImportWrite, PlanEntry, WriteAction
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.membership_import import MembershipImportRepository, MembershipWriteRefused

SEASON = "2026-2027"
TODAY = datetime.date(2026, 10, 31)


def record(item_id: int, last_name: str = "WEASLEY", first_name: str = "Ginny", **overrides: Any) -> MembershipRecord:  # Any: fields
    base = MembershipRecord(
        item_id=item_id, order_ref=str(500 + item_id), order_date="2026-09-01T10:00:00+02:00", status="Processed",
        tarif_name="Loisir collège", amount=150.0, last_name=last_name, first_name=first_name,
        payer_last_name=last_name, payer_first_name="Molly", payer_email="parent@terrier.example",
        birth_date="2013-08-11", birth_date_raw="11/08/2013", licence="",
        options={"Assurance Base +": 11.0},
        custom_fields={"Date de naissance de l'adhérent": "11/08/2013", "Ville": "Jonage", "Téléphone ": "0611223344"},
    )
    return replace(base, **overrides)


def create(rec: MembershipRecord) -> ImportWrite:
    return ImportWrite(PlanEntry(rec, Bucket.NEW, "nouveau"), WriteAction.CREATE)


class TestMembershipImportRepository(MemberDbTestCase):

    def rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:  # Any: SQLite values
        conn = SqliteDatabase.get_connection()
        try:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def test_purchases_get_the_helloasso_columns_and_a_unique_item_id(self) -> None:
        columns = {row["name"] for row in self.rows("PRAGMA table_info(purchases)")}
        self.assertLessEqual({"helloasso_item_id", "helloasso_status", "helloasso_amount", "helloasso_tarif"}, columns)

        MembershipImportRepository.apply([create(record(1))], SEASON)
        conn = SqliteDatabase.get_connection()
        try:
            purchase = conn.execute("SELECT order_id, user_id FROM purchases").fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO purchases (order_id, user_id, helloasso_item_id) VALUES (?, ?, 1)",
                             (purchase["order_id"] + 100, purchase["user_id"]))
        finally:
            conn.close()

    def test_create_writes_the_member_order_purchase_and_options(self) -> None:
        [applied] = MembershipImportRepository.apply([create(record(1))], SEASON)

        [user] = self.rows("SELECT * FROM users")
        self.assertEqual((applied.item_id, applied.action, applied.user_id), (1, WriteAction.CREATE, user["id"]))
        self.assertEqual((user["last_name"], user["first_name"], user["birth_date"], user["city"], user["phone"]),
                         ("WEASLEY", "Ginny", "2013-08-11", "Jonage", "0611223344"))
        [order] = self.rows("SELECT o.*, s.name AS season FROM orders o JOIN seasons s ON s.id = o.season_id")
        self.assertEqual((order["order_ref"], order["payer_email"], order["season"]), ("501", "parent@terrier.example", SEASON))
        [purchase] = self.rows("SELECT * FROM purchases")
        self.assertEqual(purchase["id"], applied.purchase_id)
        self.assertEqual((purchase["tarif_name"], purchase["amount"], purchase["status"]), ("Loisir collège", 150.0, "Processed"))
        self.assertEqual((purchase["helloasso_item_id"], purchase["helloasso_status"], purchase["helloasso_amount"],
                          purchase["helloasso_tarif"]), (1, "Processed", 150.0, "Loisir collège"))
        self.assertEqual(self.rows("SELECT option_name, amount FROM purchase_options"), [{"option_name": "Assurance Base +", "amount": 11.0}])

    def test_every_helloasso_status_and_waiting_list_tariff_is_kept(self) -> None:
        writes = [create(record(1, status="Refunded", amount=0.0)),
                  create(record(2, "LOVEGOOD", "Luna", status="Waiting", tarif_name="Liste d'attente cours ", amount=0.0))]

        MembershipImportRepository.apply(writes, SEASON)

        purchases = self.rows("SELECT u.last_name, p.status, p.tarif_name, p.helloasso_status FROM purchases p"
                              " JOIN users u ON u.id = p.user_id ORDER BY u.last_name")
        self.assertEqual([tuple(p.values()) for p in purchases],
                         [("LOVEGOOD", "Waiting", "Liste d'attente cours", "Waiting"), ("WEASLEY", "Refunded", "Loisir collège", "Refunded")])

    def test_writes_are_one_transaction(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            MembershipImportRepository.apply([create(record(1)), create(record(1, "LOVEGOOD", "Luna", order_ref="900"))], SEASON)

        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM users"), [{"n": 0}])
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM purchases"), [{"n": 0}])

    def test_snapshot_lists_the_members_and_their_purchases(self) -> None:
        self.seed("ORD-1", "Ginny", "WEASLEY", "Loisir collège", season="2025-2026",
                  **{"champ_Numéro de Licence FFME (6 chiffres)": "12 34 56"})
        MembershipImportRepository.apply([create(record(1, "LOVEGOOD", "Luna"))], SEASON)

        snapshot = MembershipImportRepository.snapshot()

        members = {m.last_name: m for m in snapshot.members}
        self.assertEqual((members["WEASLEY"].first_name, members["WEASLEY"].birth_date, members["WEASLEY"].licence),
                         ("Ginny", "2017-03-10", "123456"))
        purchases = {p.order_ref: p for p in snapshot.purchases}
        self.assertEqual((purchases["ORD-1"].season, purchases["ORD-1"].helloasso_item_id, purchases["ORD-1"].user_id),
                         ("2025-2026", None, members["WEASLEY"].user_id))
        self.assertEqual((purchases["501"].season, purchases["501"].helloasso_item_id, purchases["501"].status), (SEASON, 1, "Processed"))

    def test_attach_adds_the_season_to_the_member_and_only_fills_blank_fields(self) -> None:
        self.seed("ORD-1", "Ginny", "WEASLEY", "Loisir collège", season="2025-2026", **{"champ_Téléphone ": "0600000000"})
        [user] = self.rows("SELECT id FROM users")
        renewal = record(1, "Weasley", "Ginny", birth_date="2017-03-10",
                         custom_fields={"Téléphone ": "0611223344", "Ville": "Jonage"})

        [applied] = MembershipImportRepository.apply(
            [ImportWrite(PlanEntry(renewal, Bucket.RENEWAL, "renouvellement", member_id=user["id"]), WriteAction.ATTACH)], SEASON)

        self.assertEqual(applied.user_id, user["id"])
        [updated] = self.rows("SELECT * FROM users")
        self.assertEqual((updated["last_name"], updated["phone"], updated["city"]), ("WEASLEY", "0600000000", "Jonage"))
        seasons = self.rows("SELECT s.name, p.helloasso_item_id FROM purchases p JOIN orders o ON o.id = p.order_id"
                            " JOIN seasons s ON s.id = o.season_id ORDER BY s.name")
        self.assertEqual([tuple(r.values()) for r in seasons], [("2025-2026", None), (SEASON, 1)])

    def test_backfill_marks_a_former_purchase_with_its_item_id(self) -> None:
        self.seed("501", "Ginny", "WEASLEY", "Loisir collège")
        [purchase] = self.rows("SELECT id, user_id FROM purchases")
        entry = PlanEntry(record(1), Bucket.ALREADY_IMPORTED, "déjà là", purchase["user_id"], purchase["id"], backfill=True)

        MembershipImportRepository.apply([ImportWrite(entry, WriteAction.BACKFILL)], SEASON)

        self.assertEqual(self.rows("SELECT helloasso_item_id, helloasso_status, helloasso_amount, helloasso_tarif, status FROM purchases"),
                         [{"helloasso_item_id": 1, "helloasso_status": "Processed", "helloasso_amount": 150.0,
                           "helloasso_tarif": "Loisir collège", "status": "Validated"}])
        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM users"), [{"n": 1}])

    def test_a_registration_below_the_member_s_membership_this_season_is_refused(self) -> None:
        self.seed("ORD-1", "Ginny", "WEASLEY", "Loisir collège")
        [user] = self.rows("SELECT id FROM users")
        cancelled = record(1, status="Canceled", amount=0.0)

        with self.assertRaises(MembershipWriteRefused):
            MembershipImportRepository.apply(
                [create(record(2, "LOVEGOOD", "Luna")),
                 ImportWrite(PlanEntry(cancelled, Bucket.TO_REVIEW, "à vérifier", member_id=user["id"]), WriteAction.ATTACH)], SEASON)

        self.assertEqual(self.rows("SELECT COUNT(*) AS n FROM purchases"), [{"n": 1}])

    def test_snapshot_carries_the_last_values_read_on_helloasso(self) -> None:
        MembershipImportRepository.apply([create(record(1))], SEASON)

        [purchase] = MembershipImportRepository.snapshot().purchases

        self.assertEqual((purchase.helloasso_status, purchase.helloasso_tarif, purchase.helloasso_amount),
                         ("Processed", "Loisir collège", 150.0))

    def test_update_writes_the_changed_values_and_the_last_values_read(self) -> None:
        [applied] = MembershipImportRepository.apply([create(record(1))], SEASON)
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute("UPDATE purchases SET commentaires_correctif = 'Payé en chèque', tarif_name = 'Loisir (CRM)'")
            conn.commit()
        finally:
            conn.close()
        refunded = record(1, status="Refunded", tarif_name="Loisir collège v2")
        entry = PlanEntry(refunded, Bucket.UPDATED, "modifiée", applied.user_id, applied.purchase_id,
                          changes=(FieldChange("status", "Processed", "Processed", "Refunded"),))

        MembershipImportRepository.apply([ImportWrite(entry, WriteAction.UPDATE)], SEASON, TODAY)

        [purchase] = self.rows("SELECT status, status_normalized, tarif_name, amount, commentaires_correctif, helloasso_status,"
                               " helloasso_tarif, helloasso_amount FROM purchases")
        self.assertEqual(purchase, {"status": "Refunded", "status_normalized": "Refunded", "tarif_name": "Loisir (CRM)", "amount": 150.0,
                                    "commentaires_correctif": "Payé en chèque\nImport HelloAsso du 31/10", "helloasso_status": "Refunded",
                                    "helloasso_tarif": "Loisir collège v2", "helloasso_amount": 150.0})

    def test_written_purchases_carry_the_import_marker(self) -> None:
        MembershipImportRepository.apply([create(record(1))], SEASON, TODAY)
        MembershipImportRepository.apply([create(record(2, "LOVEGOOD", "Luna"))], SEASON, TODAY)

        self.assertEqual([r["commentaires_correctif"] for r in self.rows("SELECT commentaires_correctif FROM purchases ORDER BY id")],
                         ["Import HelloAsso du 31/10", "Import HelloAsso du 31/10"])
