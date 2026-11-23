"""Reading SQLite databases written before users.gender became users.sex (plans/sex-enum.md)."""

from __future__ import annotations

import sqlite3

import pytest

from infrastructure.sqlite.schema_v2 import rename_gender_column, sex_code


def _old_database(tracked: bool) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, last_name TEXT, gender TEXT)")
    conn.executemany("INSERT INTO users VALUES (?, ?, ?)", [(1, "GRANGER", "Femme"), (2, "WEASLEY", "m"), (3, "LOVEGOOD", "X"),
                                                             (4, "POTTER", None)])
    if tracked:  # a Firestore cache (cloud_sync tracking tables)
        conn.execute("CREATE TABLE _fs_changes (tbl TEXT, pk TEXT, seq INTEGER)")
    return conn


def test_rename_gender_column_converts_a_plain_database() -> None:
    conn = _old_database(tracked=False)
    rename_gender_column(conn.cursor())
    assert conn.execute("SELECT id, sex FROM users ORDER BY id").fetchall() == [(1, "F"), (2, "H"), (3, None), (4, None)]
    rename_gender_column(conn.cursor())  # idempotent
    assert conn.execute("SELECT sex FROM users WHERE id = 1").fetchone() == ("F",)


def test_rename_gender_column_only_renames_a_firestore_cache() -> None:
    # Converting would fire the tracking triggers and push the values; the cache is rebuilt instead (CACHE_FORMAT)
    conn = _old_database(tracked=True)
    rename_gender_column(conn.cursor())
    assert conn.execute("SELECT sex FROM users WHERE id = 1").fetchone() == ("Femme",)


def test_sex_code_logs_the_order_never_the_value_holder(caplog: pytest.LogCaptureFixture) -> None:
    assert sex_code("Féminin", "HA-1") == "F"
    assert sex_code("", "HA-2") is None
    assert not caplog.records
    assert sex_code("X", "HA-3") is None
    assert [r.getMessage() for r in caplog.records] == ["Sexe non reconnu pour la commande HA-3 : enregistré comme non renseigné"]
