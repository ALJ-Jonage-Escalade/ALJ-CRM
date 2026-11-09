"""Cache SQLite local : connexion, déclencheurs de suivi `_fs_*`, état et accès aux lignes."""
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from infrastructure.firestore.client import FirestoreError
from infrastructure.firestore.cloud_sync.common import TRACKED_TABLES

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA recursive_triggers=ON")
    return conn


def table_exists(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone() is not None


def table_columns(conn, table: str) -> List[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def table_pk(conn, table: str) -> List[str]:
    cols = [(r[5], r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")') if r[5]]
    return [c for _, c in sorted(cols)]


def tracked_tables(conn) -> List[str]:
    return [t for t in TRACKED_TABLES if table_exists(conn, t)]


def install_tracking(conn):
    """Crée les tables techniques et les déclencheurs de suivi (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _fs_changes (tbl TEXT NOT NULL, pk TEXT NOT NULL,
            seq INTEGER NOT NULL, PRIMARY KEY (tbl, pk));
        CREATE TABLE IF NOT EXISTS _fs_counter (id INTEGER PRIMARY KEY CHECK (id = 1), n INTEGER NOT NULL);
        INSERT OR IGNORE INTO _fs_counter (id, n) VALUES (1, 0);
        CREATE TABLE IF NOT EXISTS _fs_base (tbl TEXT NOT NULL, pk TEXT NOT NULL,
            data TEXT NOT NULL, ut TEXT, PRIMARY KEY (tbl, pk));
        CREATE TABLE IF NOT EXISTS _fs_state (k TEXT PRIMARY KEY, v TEXT);
    """)
    for t in tracked_tables(conn):
        pk = table_pk(conn, t)
        if not pk:
            continue

        def pk_expr(prefix):
            return "json_array(" + ", ".join(f'{prefix}."{c}"' for c in pk) + ")"

        def log(prefix):
            return (f"DELETE FROM _fs_changes WHERE tbl = '{t}' AND pk = {pk_expr(prefix)}; "  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
                    f"INSERT INTO _fs_changes (tbl, pk, seq) VALUES ('{t}', {pk_expr(prefix)}, "
                    f"(SELECT n FROM _fs_counter WHERE id = 1)); ")
        guard = "WHEN NOT EXISTS (SELECT 1 FROM _fs_state WHERE k = 'applying' AND v = '1')"
        bump = "UPDATE _fs_counter SET n = n + 1 WHERE id = 1; "
        conn.executescript(f"""
            CREATE TRIGGER IF NOT EXISTS "_fs_{t}_ai" AFTER INSERT ON "{t}" {guard}
            BEGIN {bump}{log('NEW')}END;
            CREATE TRIGGER IF NOT EXISTS "_fs_{t}_au" AFTER UPDATE ON "{t}" {guard}
            BEGIN {bump}{log('OLD')}{log('NEW')}END;
            CREATE TRIGGER IF NOT EXISTS "_fs_{t}_ad" AFTER DELETE ON "{t}" {guard}
            BEGIN {bump}{log('OLD')}END;
        """)


def get_state(conn, key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        r = conn.execute("SELECT v FROM _fs_state WHERE k = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return r[0] if r else default


def set_state(conn, key: str, value: str):
    conn.execute("INSERT INTO _fs_state (k, v) VALUES (?, ?) "
                 "ON CONFLICT(k) DO UPDATE SET v = excluded.v", (key, value))


def pending_count(conn) -> int:
    try:
        return conn.execute("SELECT COUNT(*) FROM _fs_changes").fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def _pk_string(conn, values: List[Any]) -> str:
    return conn.execute("SELECT json_array(" + ",".join("?" * len(values)) + ")", values).fetchone()[0]


def _where(pk: List[str]) -> str:
    return " AND ".join(f'"{c}" IS ?' for c in pk)


def _read_row(conn, table: str, pk: List[str], values: List[Any]) -> Optional[Dict[str, Any]]:
    r = conn.execute(f'SELECT * FROM "{table}" WHERE {_where(pk)}', values).fetchone()  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
    return dict(r) if r else None


def _upsert_row(conn, table: str, cols: List[str], pk: List[str], data: Dict[str, Any]):
    use = [c for c in cols if c in data]
    if not all(c in use for c in pk):
        raise FirestoreError(f"Document {table} sans clé primaire complète")
    placeholders = ", ".join("?" for _ in use)
    col_sql = ", ".join(f'"{c}"' for c in use)
    upd = [c for c in use if c not in pk]
    sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders}) ON CONFLICT({", ".join(chr(34) + c + chr(34) for c in pk)}) '  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
    sql += ("DO UPDATE SET " + ", ".join(f'"{c}" = excluded."{c}"' for c in upd)) if upd else "DO NOTHING"
    conn.execute(sql, [data[c] for c in use])


def _set_base(conn, table: str, pk_str: str, data: Dict[str, Any], ut: Optional[str]):
    conn.execute("INSERT INTO _fs_base (tbl, pk, data, ut) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(tbl, pk) DO UPDATE SET data = excluded.data, ut = excluded.ut",
                 (table, pk_str, json.dumps(data, ensure_ascii=False), ut))


def _get_base(conn, table: str, pk_str: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    r = conn.execute("SELECT data, ut FROM _fs_base WHERE tbl = ? AND pk = ?", (table, pk_str)).fetchone()
    if not r:
        return None, None
    return json.loads(r[0]), r[1]


class _Applying:
    """Désactive les déclencheurs de suivi dans la transaction courante."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        set_state(self.conn, "applying", "1")

    def __exit__(self, *exc):
        set_state(self.conn, "applying", "0")



class _Resume:
    """Réactive temporairement le suivi (pour qu'une renumérotation soit envoyée)."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        set_state(self.conn, "applying", "0")

    def __exit__(self, *exc):
        set_state(self.conn, "applying", "1")

