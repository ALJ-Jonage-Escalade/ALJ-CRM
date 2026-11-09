"""Club keys of the climbing wall in the SQLite cache (tables keys, key_assignments; plans/club-keys.md)."""

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


class KeyRow(TypedDict):
    id: int
    code: str
    status: str
    holder: Optional[HolderRow]  # the open assignment


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
                       (SELECT MAX(s.name) FROM purchases p JOIN orders o ON o.id = p.order_id
                        JOIN seasons s ON s.id = o.season_id WHERE p.user_id = a.user_id) AS last_season
                FROM keys k
                LEFT JOIN key_assignments a ON a.key_id = k.id AND a.returned_on IS NULL
                LEFT JOIN users u ON u.id = a.user_id
                ORDER BY k.id
            """).fetchall()
            return [KeyRow(id=r["id"], code=r["code"], status=r["status"],
                           holder=HolderRow(user_id=r["user_id"], last_name=r["last_name"] or "", first_name=r["first_name"] or "",
                                            given_on=r["given_on"], comment=r["comment"], last_season=r["last_season"] or "") if r["user_id"] is not None else None)
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
            return KeyRow(id=key_id, code=code, status="available", holder=None)
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
