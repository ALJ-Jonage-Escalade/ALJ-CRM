"""Club keys of the climbing wall in the SQLite cache (tables keys, plans/club-keys.md)."""

from __future__ import annotations

import datetime
import sqlite3
from typing import List, TypedDict

from domain.errors import Conflict
from infrastructure.sqlite.connection import SqliteDatabase


class KeyRow(TypedDict):
    id: int
    code: str
    status: str


def _connect() -> sqlite3.Connection:
    SqliteDatabase.setup_database()
    return SqliteDatabase.get_connection()


class KeyRepository:
    @classmethod
    def list_keys(cls) -> List[KeyRow]:
        conn = _connect()
        try:
            rows = conn.execute("SELECT id, code, status FROM keys ORDER BY id").fetchall()
            return [KeyRow(id=r["id"], code=r["code"], status=r["status"]) for r in rows]
        finally:
            conn.close()

    @classmethod
    def add_key(cls, code: str) -> KeyRow:
        """A new available key; Conflict when another key has this code (whatever its case)."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
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
            return KeyRow(id=key_id, code=code, status="available")
        finally:
            conn.close()
