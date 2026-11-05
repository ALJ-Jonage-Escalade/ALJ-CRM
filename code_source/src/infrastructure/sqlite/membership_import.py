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
from typing import Optional

from domain.members.membership_import import ImportWrite, KnownMember, KnownPurchase, MembersSnapshot, WriteAction
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")


class MembershipWriteRefused(Exception):
    """A write the members base refuses (nothing of the import is then written)."""


@dataclass(frozen=True)
class AppliedWrite:
    item_id: int
    action: WriteAction
    user_id: int
    purchase_id: int


def _record_helloasso_values(cur: sqlite3.Cursor, purchase_id: int, write: ImportWrite) -> None:
    """The registration the purchase comes from, and the values HelloAsso gave for it."""
    record = write.entry.record
    cur.execute("UPDATE purchases SET helloasso_item_id = ?, helloasso_status = ?, helloasso_amount = ?, helloasso_tarif = ?"
                " WHERE id = ?", (record.item_id, record.status, record.amount, record.tarif_name.strip(), purchase_id))


def _add_membership(cur: sqlite3.Cursor, write: ImportWrite, user_id: int, season_id: int, now_iso: str) -> AppliedWrite:
    """The season's order, purchase and insurance options of the registration, for this member."""
    fields = write.entry.record.legacy_fields()
    order_id = schema_v2.upsert_order_v2(cur, fields["order_ref"], fields["order_date"], fields["status"],
                                         fields["payer_lastName"], fields["payer_firstName"], fields["payer_email"],
                                         season_id, now_iso)
    purchase_id = schema_v2.insert_purchase_v2(cur, order_id, user_id, fields, now_iso, legacy_season_id=season_id)
    if purchase_id is None:  # a membership of higher priority this season (purchase_priority_score)
        record = write.entry.record
        raise MembershipWriteRefused(f"{record.last_name} {record.first_name} a déjà une inscription plus prioritaire cette saison "
                                     f"(statut, liste d'attente ou montant) : l'inscription HelloAsso {write.item_id} n'est pas importée.")
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


def _assign(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    """The registration given by hand to a member: their membership of the season that is not from HelloAsso
    (entry.purchase_id) takes the HelloAsso order and values, or a membership is added. The member is left as typed."""
    entry, record = write.entry, write.entry.record
    if entry.member_id is None:
        raise ValueError(f"Inscription {write.item_id} : adhérent à rattacher non indiqué")
    if entry.purchase_id is None:
        return _add_membership(cur, write, entry.member_id, season_id, now_iso)
    fields = record.legacy_fields()
    order_id = schema_v2.upsert_order_v2(cur, fields["order_ref"], fields["order_date"], fields["status"],
                                         fields["payer_lastName"], fields["payer_firstName"], fields["payer_email"],
                                         season_id, now_iso)
    row = cur.execute("SELECT order_id FROM purchases WHERE id = ? AND user_id = ?", (entry.purchase_id, entry.member_id)).fetchone()
    if row is None:
        raise MembershipWriteRefused(f"L'adhésion à reprendre de l'inscription HelloAsso {write.item_id} a disparu.")
    cur.execute("UPDATE purchases SET order_id = ?, tarif_name = ?, amount = ?, status = ?, status_normalized = ?, updated_at = ?"
                " WHERE id = ?", (order_id, record.tarif_name.strip(), record.amount, record.status,
                                  schema_v2.normalize_status(record.status), now_iso, entry.purchase_id))
    cur.execute("DELETE FROM purchase_options WHERE purchase_id = ?", (entry.purchase_id,))
    schema_v2.insert_options_v2(cur, entry.purchase_id, fields)
    _record_helloasso_values(cur, entry.purchase_id, write)
    # The manual order taken over, left without purchase
    cur.execute("DELETE FROM orders WHERE id = ? AND NOT EXISTS (SELECT 1 FROM purchases WHERE order_id = ?)", (row[0], row[0]))
    return AppliedWrite(write.item_id, write.action, entry.member_id, entry.purchase_id)


def _backfill(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    entry = write.entry
    if entry.member_id is None or entry.purchase_id is None:
        raise ValueError(f"Inscription {write.item_id} : achat à marquer non indiqué")
    _record_helloasso_values(cur, entry.purchase_id, write)
    return AppliedWrite(write.item_id, write.action, entry.member_id, entry.purchase_id)


def _update(cur: sqlite3.Cursor, write: ImportWrite, season_id: int, now_iso: str) -> AppliedWrite:
    """The values HelloAsso changed (entry.changes) written on the purchase; the other values stay as in the CRM."""
    entry, record = write.entry, write.entry.record
    if entry.member_id is None or entry.purchase_id is None:
        raise ValueError(f"Inscription {write.item_id} : achat à mettre à jour non indiqué")
    new_values = {"status": record.status, "tarif_name": record.tarif_name.strip(), "amount": record.amount}
    for change in entry.changes:
        column = change.field
        cur.execute(f'UPDATE purchases SET "{column}" = ?, updated_at = ? WHERE id = ?',  # noqa: S608 - column: a key of new_values
                    (new_values[column], now_iso, entry.purchase_id))
        if column == "status":
            cur.execute("UPDATE purchases SET status_normalized = ? WHERE id = ?", (schema_v2.normalize_status(record.status), entry.purchase_id))
    _record_helloasso_values(cur, entry.purchase_id, write)
    return AppliedWrite(write.item_id, write.action, entry.member_id, entry.purchase_id)


# Purchases written for the members (not a back-fill, which only marks a purchase with its item id)
_MARKED = (WriteAction.CREATE, WriteAction.ATTACH, WriteAction.UPDATE, WriteAction.ASSIGN)


def import_marker(day: datetime.date) -> str:
    return f"Import HelloAsso du {day.strftime('%d/%m')}"


def assign_note(write: ImportWrite, day: datetime.date, author: str) -> str:
    """The lines a registration given by hand adds to the membership comment: the admin's comment, then who it was."""
    record = write.entry.record
    return (f"[{day.strftime('%d/%m/%Y')}] {write.comment}\n"
            f"Inscription HelloAsso au nom de {record.last_name} {record.first_name} (commande {record.order_ref}) rattachée par {author}")


def _append_marker(cur: sqlite3.Cursor, purchase_id: int, marker: str) -> None:
    """The marker appended to the purchase's comment, on its own line (the comment is kept)."""
    row = cur.execute("SELECT commentaires_correctif FROM purchases WHERE id = ?", (purchase_id,)).fetchone()
    comment = str((row[0] if row else "") or "").rstrip()
    if comment.endswith(marker):
        return
    cur.execute("UPDATE purchases SET commentaires_correctif = ? WHERE id = ?", (f"{comment}\n{marker}" if comment else marker, purchase_id))


_WRITERS = {WriteAction.CREATE: _create, WriteAction.ATTACH: _attach, WriteAction.BACKFILL: _backfill, WriteAction.UPDATE: _update,
            WriteAction.ASSIGN: _assign}

_SNAPSHOT_PURCHASES = """
    SELECT p.id, p.user_id, o.order_ref, s.name AS season, p.helloasso_item_id, p.status, p.tarif_name, p.amount,
           p.helloasso_status, p.helloasso_tarif, p.helloasso_amount
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
                                       status=row["status"] or "", tarif_name=row["tarif_name"] or "", amount=float(row["amount"] or 0.0),
                                       helloasso_status=row["helloasso_status"], helloasso_tarif=row["helloasso_tarif"],
                                       helloasso_amount=row["helloasso_amount"])
                         for row in conn.execute(_SNAPSHOT_PURCHASES)]
            return MembersSnapshot(members=members, purchases=purchases)
        finally:
            conn.close()

    @classmethod
    def apply(cls, writes: list[ImportWrite], season: str, day: Optional[datetime.date] = None, author: str = "") -> list[AppliedWrite]:
        """Applies the writes in one transaction: all of them, or none (the error is raised). The purchases written get
        "Import HelloAsso du JJ/MM" (`day`, today by default) appended to their comment, after the comment and author
        (e-mail of the admin) of a registration given by hand."""
        day = day or datetime.date.today()
        marker = import_marker(day)
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cur = conn.cursor()
            now_iso = datetime.datetime.now().isoformat(timespec="seconds")
            season_id = schema_v2.resolve_season_id(cur, season)
            applied = [_WRITERS[write.action](cur, write, season_id, now_iso) for write in writes]
            for write, written in zip(writes, applied, strict=True):
                if written.action == WriteAction.ASSIGN:
                    _append_marker(cur, written.purchase_id, assign_note(write, day, author))
                if written.action in _MARKED:
                    _append_marker(cur, written.purchase_id, marker)
            conn.commit()
            logger.info("Import HelloAsso : %d inscription(s) écrite(s) pour la saison %s", len(applied), season)
            return applied
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
