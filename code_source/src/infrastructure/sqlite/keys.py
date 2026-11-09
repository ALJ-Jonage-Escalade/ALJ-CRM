"""Club keys of the climbing wall in the SQLite cache (tables keys, key_assignments, key_events; plans/club-keys.md)."""

from __future__ import annotations

import datetime
import sqlite3
from typing import List, Optional, Set, TypedDict

from domain.errors import Conflict
from domain.members.view import is_cancelled
from infrastructure.sqlite.connection import SqliteDatabase


class HolderRow(TypedDict):
    user_id: int
    last_name: str
    first_name: str
    given_on: str
    comment: str
    last_season: str  # latest season they had a membership in (their record), "" without any


class ArchiveRow(TypedDict):
    date: str
    comment: str


class KeyRow(TypedDict):
    id: int
    code: str
    status: str
    holder: Optional[HolderRow]  # the open assignment
    archive: Optional[ArchiveRow]  # when and why an archived key was archived


class AssignmentRow(TypedDict):
    id: int
    key_id: int
    user_id: int
    last_name: str
    first_name: str
    given_on: str
    returned_on: Optional[str]  # None while held
    comment: str
    return_comment: str
    by: str


class EventRow(TypedDict):
    id: int
    type: str  # archived, restored, renamed, assignment_deleted
    date: str
    comment: str
    by: str


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    SqliteDatabase.setup_database()
    return SqliteDatabase.get_connection()


class KeyRepository:
    @classmethod
    def list_keys(cls) -> List[KeyRow]:
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT k.id, k.code, k.status, a.user_id, a.given_on, a.comment, u.last_name, u.first_name,
                       e.date AS archived_on, e.comment AS archive_comment,
                       (SELECT MAX(s.name) FROM purchases p JOIN orders o ON o.id = p.order_id
                        JOIN seasons s ON s.id = o.season_id WHERE p.user_id = a.user_id) AS last_season
                FROM keys k
                LEFT JOIN key_assignments a ON a.key_id = k.id AND a.returned_on IS NULL
                LEFT JOIN users u ON u.id = a.user_id
                LEFT JOIN key_events e ON k.status = 'archived' AND e.id = (
                    SELECT MAX(id) FROM key_events WHERE key_id = k.id AND type = 'archived')
                ORDER BY k.id
            """).fetchall()
            return [KeyRow(id=r["id"], code=r["code"], status=r["status"],
                           holder=HolderRow(user_id=r["user_id"], last_name=r["last_name"] or "", first_name=r["first_name"] or "",
                                            given_on=r["given_on"], comment=r["comment"], last_season=r["last_season"] or "") if r["user_id"] is not None else None,
                           archive=ArchiveRow(date=r["archived_on"], comment=r["archive_comment"]) if r["archived_on"] else None)
                    for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_key(cls, key_id: int) -> Optional[KeyRow]:
        return next((k for k in cls.list_keys() if k["id"] == key_id), None)

    @classmethod
    def key_held_by(cls, user_id: int) -> Optional[str]:
        """Code of the key this person holds, if any."""
        conn = _connect()
        try:
            row = conn.execute("SELECT k.code FROM key_assignments a JOIN keys k ON k.id = a.key_id"
                               " WHERE a.user_id = ? AND a.returned_on IS NULL", (user_id,)).fetchone()
            return row["code"] if row else None
        finally:
            conn.close()

    @classmethod
    def members_of_season(cls, season_name: str) -> Set[int]:
        """Ids of the people with a membership of the season that was not cancelled."""
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT p.user_id, p.status FROM purchases p
                JOIN orders o ON o.id = p.order_id JOIN seasons s ON s.id = o.season_id
                WHERE s.name = ? AND p.user_id IS NOT NULL
            """, (season_name,)).fetchall()
            return {r["user_id"] for r in rows if not is_cancelled(r["status"])}
        finally:
            conn.close()

    @classmethod
    def add_key(cls, code: str) -> KeyRow:
        """A new available key; Conflict when another key has this code (whatever its case)."""
        now = _now()
        conn = _connect()
        try:
            try:
                cursor = conn.execute("INSERT INTO keys (code, status, created_at, updated_at) VALUES (?, 'available', ?, ?)",
                                      (code, now, now))
            except sqlite3.IntegrityError as e:
                raise Conflict(f"La clé « {code} » existe déjà.", "duplicate_code") from e
            conn.commit()
            key_id = cursor.lastrowid
            assert key_id is not None  # noqa: S101 - set by the INSERT
            return KeyRow(id=key_id, code=code, status="available", holder=None, archive=None)
        finally:
            conn.close()

    @classmethod
    def assign(cls, key_id: int, user_id: int, given_on: str, comment: str, by: str) -> None:
        """Opens an assignment and marks the key assigned, in one transaction (the rules are the service's)."""
        now = _now()
        conn = _connect()
        try:
            conn.execute("INSERT INTO key_assignments (key_id, user_id, given_on, comment, by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                         (key_id, user_id, given_on, comment, by, now))
            conn.execute("UPDATE keys SET status = 'assigned', updated_at = ? WHERE id = ?", (now, key_id))
            conn.commit()
        except sqlite3.IntegrityError as e:
            conn.rollback()
            raise Conflict("La clé ou l'adhérent a déjà une attribution en cours.", "key_not_available") from e
        finally:
            conn.close()

    @classmethod
    def close_assignment(cls, key_id: int, returned_on: str, comment: str) -> None:
        """Closes the key's open assignment and makes it available."""
        now = _now()
        conn = _connect()
        try:
            conn.execute("UPDATE key_assignments SET returned_on = ?, return_comment = ? WHERE key_id = ? AND returned_on IS NULL",
                         (returned_on, comment, key_id))
            conn.execute("UPDATE keys SET status = 'available', updated_at = ? WHERE id = ?", (now, key_id))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def assignments(cls, key_id: int) -> List[AssignmentRow]:
        """The key's assignments, oldest first."""
        conn = _connect()
        try:
            rows = conn.execute("""
                SELECT a.id, a.key_id, a.user_id, a.given_on, a.returned_on, a.comment, a.return_comment, a.by,
                       u.last_name, u.first_name
                FROM key_assignments a LEFT JOIN users u ON u.id = a.user_id
                WHERE a.key_id = ? ORDER BY a.given_on, a.id
            """, (key_id,)).fetchall()
            return [_assignment(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def get_assignment(cls, assignment_id: int) -> Optional[AssignmentRow]:
        conn = _connect()
        try:
            row = conn.execute("""
                SELECT a.id, a.key_id, a.user_id, a.given_on, a.returned_on, a.comment, a.return_comment, a.by,
                       u.last_name, u.first_name
                FROM key_assignments a LEFT JOIN users u ON u.id = a.user_id WHERE a.id = ?
            """, (assignment_id,)).fetchone()
            return _assignment(row) if row else None
        finally:
            conn.close()

    @classmethod
    def events(cls, key_id: int) -> List[EventRow]:
        """The key's events, oldest first."""
        conn = _connect()
        try:
            rows = conn.execute("SELECT id, type, date, comment, by FROM key_events WHERE key_id = ? ORDER BY date, id",
                                (key_id,)).fetchall()
            return [EventRow(id=r["id"], type=r["type"], date=r["date"], comment=r["comment"], by=r["by"]) for r in rows]
        finally:
            conn.close()

    @classmethod
    def rename(cls, key_id: int, code: str, event_comment: str, by: str) -> None:
        """New code (Conflict when another key has it) and its `renamed` event, in one transaction."""
        now = _now()
        conn = _connect()
        try:
            try:
                conn.execute("UPDATE keys SET code = ?, updated_at = ? WHERE id = ?", (code, now, key_id))
            except sqlite3.IntegrityError as e:
                raise Conflict(f"La clé « {code} » existe déjà.", "duplicate_code") from e
            _add_event(conn, key_id, "renamed", now[:10], event_comment, by)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def update_assignment(cls, assignment_id: int, given_on: str, returned_on: Optional[str], comment: str, return_comment: str) -> None:
        conn = _connect()
        try:
            conn.execute("UPDATE key_assignments SET given_on = ?, returned_on = ?, comment = ?, return_comment = ? WHERE id = ?",
                         (given_on, returned_on, comment, return_comment, assignment_id))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def delete_assignment(cls, assignment: AssignmentRow, event_comment: str, by: str) -> None:
        """Deletes an assignment entered by mistake, records it as an event; an open one leaves the key available."""
        now = _now()
        conn = _connect()
        try:
            conn.execute("DELETE FROM key_assignments WHERE id = ?", (assignment["id"],))
            if assignment["returned_on"] is None:
                conn.execute("UPDATE keys SET status = 'available', updated_at = ? WHERE id = ?", (now, assignment["key_id"]))
            _add_event(conn, assignment["key_id"], "assignment_deleted", now[:10], event_comment, by)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def archive(cls, key_id: int, archived_on: str, comment: str, by: str) -> None:
        """Archives the key, ending its open assignment at that date (the reason as its return comment)."""
        now = _now()
        conn = _connect()
        try:
            conn.execute("UPDATE key_assignments SET returned_on = ?, return_comment = ? WHERE key_id = ? AND returned_on IS NULL",
                         (archived_on, comment, key_id))
            conn.execute("UPDATE keys SET status = 'archived', updated_at = ? WHERE id = ?", (now, key_id))
            _add_event(conn, key_id, "archived", archived_on, comment, by)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def restore(cls, key_id: int, comment: str, by: str) -> None:
        now = _now()
        conn = _connect()
        try:
            conn.execute("UPDATE keys SET status = 'available', updated_at = ? WHERE id = ?", (now, key_id))
            _add_event(conn, key_id, "restored", now[:10], comment, by)
            conn.commit()
        finally:
            conn.close()


def _assignment(r: sqlite3.Row) -> AssignmentRow:
    return AssignmentRow(id=r["id"], key_id=r["key_id"], user_id=r["user_id"], last_name=r["last_name"] or "",
                         first_name=r["first_name"] or "", given_on=r["given_on"], returned_on=r["returned_on"],
                         comment=r["comment"], return_comment=r["return_comment"], by=r["by"])


def _add_event(conn: sqlite3.Connection, key_id: int, type_: str, date: str, comment: str, by: str) -> None:
    conn.execute("INSERT INTO key_events (key_id, type, date, comment, by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (key_id, type_, date, comment, by, _now()))
