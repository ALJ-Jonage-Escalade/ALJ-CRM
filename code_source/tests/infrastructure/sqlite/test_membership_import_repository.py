"""Writes of the HelloAsso membership import (infrastructure/sqlite/membership_import.py) on a temporary member
database: schema, one transaction, every HelloAsso value kept (fake data only)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Any

from support.member_db import MemberDbTestCase

from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import Bucket, ImportWrite, PlanEntry, WriteAction
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.membership_import import MembershipImportRepository

SEASON = "2026-2027"


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
