"""Construction complète du cache depuis Firestore et export initial d'une base vers Firestore."""
import datetime
import logging
import os
import sqlite3
from typing import Any, Callable, Dict, List, Optional

from infrastructure.firestore.cloud_sync.cache import (
    _pk_string,
    _set_base,
    _TrackingSuspended,
    _upsert_row,
    connect,
    get_state,
    install_tracking,
    set_state,
    table_columns,
    table_exists,
    table_pk,
    tracked_tables,
)
from infrastructure.firestore.cloud_sync.common import (
    CACHE_FORMAT,
    COMMIT_CHUNK,
    TRACKED_TABLES,
    SyncReport,
    collection_for,
    doc_id_for,
    ts_key,
    upgrade_legacy_fields,
)
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")

def create_schema(path: str):
    """Crée une base vide au schéma de l'application (SqliteDatabase)."""
    SqliteDatabase.apply_schema(path)  # the application keeps its own file meanwhile


def _remove_db_files(path: str):
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            os.remove(path + suffix)
        except FileNotFoundError:
            pass


def build_cache(path: str, store, schema_factory: Callable[[str], None] = create_schema,
                backup_dir: Optional[str] = None) -> SyncReport:
    """Reconstruit intégralement le cache `path` depuis Firestore (remplacement atomique)."""
    report = SyncReport(loaded={})
    building_path = path + ".building"
    _remove_db_files(building_path)
    schema_factory(building_path)
    conn = connect(building_path)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("BEGIN")
        for table in TRACKED_TABLES:
            if table_exists(conn, table):
                conn.execute(f'DELETE FROM "{table}"')  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info
        conn.execute("COMMIT")
        install_tracking(conn)
        conn.execute("BEGIN")
        with _TrackingSuspended(conn):
            for table in tracked_tables(conn):
                cols, pk = table_columns(conn, table), table_pk(conn, table)
                docs = store.list_all(collection_for(table))
                loaded_count, watermark = 0, "1970-01-01T00:00:00Z"
                for doc in docs:
                    if doc.get("modified_at") and ts_key(doc["modified_at"]) > ts_key(watermark):
                        watermark = doc["modified_at"]
                    if doc["deleted"]:
                        continue
                    fields = upgrade_legacy_fields(table, doc["fields"])
                    remote = {c: fields[c] for c in cols if c in fields}
                    _upsert_row(conn, table, cols, pk, remote)
                    _set_base(conn, table, _pk_string(conn, [remote[c] for c in pk]), remote, doc["update_time"])
                    loaded_count += 1
                set_state(conn, f"wm:{table}", watermark)
                report["loaded"][table] = loaded_count
        conn.execute("DELETE FROM _fs_changes")
        set_state(conn, "format", CACHE_FORMAT)
        set_state(conn, "project", store.project_id)
        set_state(conn, "built_at", datetime.datetime.now().isoformat(timespec="seconds"))
        conn.execute("COMMIT")
    finally:
        conn.close()
    if os.path.exists(path):
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                current_cache = sqlite3.connect(path)
                backup_copy = sqlite3.connect(os.path.join(backup_dir, f"database_avant_firestore_{stamp}.db"))
                current_cache.backup(backup_copy)
                backup_copy.close()
                current_cache.close()
            except Exception as e:
                logger.warning(f"[CLOUD_DB] Sauvegarde de l'ancien cache impossible : {e}")
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
    os.replace(building_path, path)
    return report


def cache_is_valid(path: str, project_id: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        conn = connect(path)
        try:
            return (get_state(conn, "format") == CACHE_FORMAT
                    and get_state(conn, "project") == project_id)
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return False


def export_rows(conn, table: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]  # noqa: S608 - noms de tables/colonnes issus de TRACKED_TABLES et PRAGMA table_info


def import_database(src_path: str, store, by: str = "migration") -> Dict[str, int]:
    """Écrit toutes les lignes des tables suivies de `src_path` dans Firestore
    (documents complets, ré-exécutable sans doublon)."""
    conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    counts = {}
    try:
        for table in tracked_tables(conn):
            pk = table_pk(conn, table)
            writes = []
            for row in export_rows(conn, table):
                writes.append({"collection": collection_for(table), "doc_id": doc_id_for([row[c] for c in pk]),
                               "fields": row, "mask": None, "deleted": False, "by": by})
            for i in range(0, len(writes), COMMIT_CHUNK):
                store.commit(writes[i:i + COMMIT_CHUNK])
            counts[table] = len(writes)
    finally:
        conn.close()
    return counts
