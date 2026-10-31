"""Writes of the HelloAsso membership import into the members (schema v2, SQLite cache replicated to Firestore).

The writes of one import go in one transaction through the member writers of schema_v2 (the same path as the other
member writes: the tracking triggers send them to Firestore). The season is always given by the caller.
"""

from __future__ import annotations

import datetime
import logging
import sqlite3
from dataclasses import dataclass

from domain.members.membership_import import ImportWrite, WriteAction
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


def _create(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    fields = write.entry.record.legacy_fields()
    user_id, _created = schema_v2.upsert_user_v2(cur, fields, now_iso, schema_v2.build_user_field_map(cur))
    order_id = schema_v2.upsert_order_v2(cur, fields["order_ref"], fields["order_date"], fields["status"],
                                         fields["payer_lastName"], fields["payer_firstName"], fields["payer_email"],
                                         season_id, now_iso)
    purchase_id = schema_v2.insert_purchase_v2(cur, order_id, user_id, fields, now_iso, legacy_season_id=season_id)
    if purchase_id is None:  # a registration of higher priority of the same person this season (purchase_priority_score)
        cur.execute("SELECT id FROM purchases WHERE order_id = ? AND user_id = ?", (order_id, user_id))
        found = cur.fetchone()
        if found is None:
            raise sqlite3.IntegrityError(f"Inscription {write.item_id} : achat introuvable après l'import")
        purchase_id = int(found[0])
    else:
        schema_v2.insert_options_v2(cur, purchase_id, fields)
    _record_helloasso_values(cur, purchase_id, write)
    return AppliedWrite(write.item_id, write.action, user_id, purchase_id)


class MembershipImportRepository:

    @classmethod
    def apply(cls, writes: list[ImportWrite], season: str) -> list[AppliedWrite]:
        """Applies the writes in one transaction: all of them, or none (the error is raised)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cur = conn.cursor()
            now_iso = datetime.datetime.now().isoformat(timespec="seconds")
            season_id = schema_v2.resolve_season_id(cur, season)
            applied = [_create(cur, write, season_id, now_iso) for write in writes]
            conn.commit()
            logger.info("Import HelloAsso : %d inscription(s) écrite(s) pour la saison %s", len(applied), season)
            return applied
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
