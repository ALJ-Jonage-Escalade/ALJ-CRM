"""The club key tables (plans/club-keys.md) are replicated to Firestore: a key written in the cache is sent."""

from __future__ import annotations

from pathlib import Path

from infrastructure.firestore.cloud_sync.cache import connect, install_tracking
from infrastructure.sqlite.connection import SqliteDatabase


def test_a_new_key_is_queued_for_firestore(tmp_path: Path) -> None:
    path = str(tmp_path / "cache.db")
    SqliteDatabase.apply_schema(path)
    conn = connect(path)
    install_tracking(conn)
    conn.execute("INSERT INTO keys (code, status) VALUES ('12', 'available')")
    assert [r["tbl"] for r in conn.execute("SELECT tbl FROM _fs_changes")] == ["keys"]


def test_assignments_are_replicated_and_follow_renumbered_ids() -> None:
    from infrastructure.firestore.cloud_sync.common import REFERENCES, TRACKED_TABLES
    assert "key_assignments" in TRACKED_TABLES
    assert ("key_assignments", "key_id") in REFERENCES["keys"]
    assert ("key_assignments", "user_id") in REFERENCES["users"]
    assert "key_events" in TRACKED_TABLES
    assert ("key_events", "key_id") in REFERENCES["keys"]
