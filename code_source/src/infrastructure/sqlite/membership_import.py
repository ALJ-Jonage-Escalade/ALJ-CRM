"""Writes of the HelloAsso membership import into the members (schema v2, SQLite cache replicated to Firestore).

The writes of one import go in one transaction through the member writers of schema_v2 (the same path as the other
member writes: the tracking triggers send them to Firestore). The season is always given by the caller.
"""

from __future__ import annotations

import datetime
import logging
import re
import sqlite3
from dataclasses import dataclass

from domain.members.membership_import import ImportWrite, KnownMember, KnownPurchase, MembersSnapshot, WriteAction
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")


@dataclass(frozen=True)
class AppliedWrite:
    item_id: int
    action: WriteAction
    user_id: int
    purchase_id: int


def _record_helloasso_values(cur: sqlite3.Cursor, purchase_id: int, write: ImportWrite) -> None:
    """The registration the purchase comes from, and the values HelloAsso gave for it."""
    rec = write.entry.record
    cur.execute("UPDATE purchases SET helloasso_item_id = ?, helloasso_status = ?, helloasso_amount = ?, helloasso_tarif = ?"
                " WHERE id = ?", (rec.item_id, rec.status, rec.amount, rec.tarif_name.strip(), purchase_id))


def _add_membership(cur: sqlite3.Cursor, write: ImportWrite, user_id: int, season_id: int, now_iso: str) -> AppliedWrite:
    """The season's order, purchase and insurance options of the registration, for this member."""
    fields = write.entry.record.legacy_fields()
    order_id = schema_v2.upsert_order_v2(cur, fields["order_ref"], fields["order_date"], fields["status"],
                                         fields["payer_lastName"], fields["payer_firstName"], fields["payer_email"],
                                         season_id, now_iso)
    purchase_id = schema_v2.insert_purchase_v2(cur, order_id, user_id, fields, now_iso, legacy_season_id=season_id)
    if purchase_id is None:  # the planner keeps the registrations of lower priority out (purchase_priority_score)
        raise sqlite3.IntegrityError(f"Inscription {write.item_id} : une inscription plus prioritaire existe déjà")
    schema_v2.insert_options_v2(cur, purchase_id, fields)
    _record_helloasso_values(cur, purchase_id, write)
    return AppliedWrite(write.item_id, write.action, user_id, purchase_id)


def _create(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    fields = write.entry.record.legacy_fields()
    user_id, _created = schema_v2.upsert_user_v2(cur, fields, now_iso, schema_v2.build_user_field_map(cur))
    return _add_membership(cur, write, user_id, season_id, now_iso)


def _attach(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    user_id = write.entry.member_id
    if user_id is None:
        raise ValueError(f"Inscription {write.item_id} : adhérent à compléter non indiqué")
    fields = write.entry.record.legacy_fields()
    schema_v2.fill_blank_user_fields(cur, user_id, fields, now_iso, schema_v2.build_user_field_map(cur))
    return _add_membership(cur, write, user_id, season_id, now_iso)


def _backfill(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    entry = write.entry
    if entry.member_id is None or entry.purchase_id is None:
        raise ValueError(f"Inscription {write.item_id} : achat à marquer non indiqué")
    _record_helloasso_values(cur, entry.purchase_id, write)
    return AppliedWrite(write.item_id, write.action, entry.member_id, entry.purchase_id)


_WRITERS = {WriteAction.CREATE: _create, WriteAction.ATTACH: _attach, WriteAction.BACKFILL: _backfill}

_SNAPSHOT_PURCHASES = """
    SELECT p.id, p.user_id, o.order_ref, s.name AS season, p.helloasso_item_id, p.status, p.tarif_name, p.amount
    FROM purchases p JOIN orders o ON o.id = p.order_id LEFT JOIN seasons s ON s.id = o.season_id
"""


class MembershipImportRepository:

    @classmethod
    def snapshot(cls) -> MembersSnapshot:
        """Every member and every purchase (all seasons), with the keys the import planner recognises them by."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            members = [KnownMember(user_id=row["id"], last_name=row["last_name"] or "", first_name=row["first_name"] or "",
                                   birth_date=row["birth_date"] or "", licence=re.sub(r"\D", "", row["licence_ffme"] or ""))
                       for row in conn.execute("SELECT id, last_name, first_name, birth_date, licence_ffme FROM users")]
            purchases = [KnownPurchase(purchase_id=row["id"], user_id=row["user_id"], order_ref=str(row["order_ref"] or ""),
                                       season=row["season"] or "", helloasso_item_id=row["helloasso_item_id"],
                                       status=row["status"] or "", tarif_name=row["tarif_name"] or "", amount=float(row["amount"] or 0.0))
                         for row in conn.execute(_SNAPSHOT_PURCHASES)]
            return MembersSnapshot(members=members, purchases=purchases)
        finally:
            conn.close()

    @classmethod
    def apply(cls, writes: list[ImportWrite], season: str) -> list[AppliedWrite]:
        """Applies the writes in one transaction: all of them, or none (the error is raised)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cur = conn.cursor()
            now_iso = datetime.datetime.now().isoformat(timespec="seconds")
            season_id = schema_v2.resolve_season_id(cur, season)
            applied = [_WRITERS[write.action](cur, write, season_id, now_iso) for write in writes]
            conn.commit()
            logger.info("Import HelloAsso : %d inscription(s) écrite(s) pour la saison %s", len(applied), season)
            return applied
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
