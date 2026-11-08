"""
Base principale des adhérents adossée à Firestore.

Depuis la migration (v2.4.0), la **source de vérité** des tables de `database.db`
(adhérents, commandes, inscriptions, options, saisons, planning, modèles d'e-mails,
réglages, cache de géocodage) est Firestore : une collection `crm_<table>` par
table, un document par ligne (ID = clé primaire SQLite).

Le fichier `database.db` local devient un **cache** reconstruit depuis Firestore :
tout le code existant (repositories de infrastructure/sqlite, vue `v_adherents_legacy`, SQL brut des
pages) continue de lire et d'écrire en SQL, sans modification.

Mécanisme :
- des déclencheurs SQLite (`_fs_*`) notent chaque ligne insérée / modifiée /
  supprimée dans `_fs_changes` ;
- `flush()` envoie ces lignes à Firestore, **champ par champ** (seules les
  colonnes modifiées depuis la dernière synchronisation sont écrites, avec la
  précondition `updateTime`) : deux postes qui modifient des champs différents
  d'un même adhérent ne s'écrasent plus ;
- `pull()` récupère les documents modifiés ailleurs (champ `_modified_at`) et
  les fusionne dans le cache (fusion à 3 voies si la ligne a aussi été modifiée
  localement) ;
- une suppression devient un document « tombe » (`_deleted: true`) pour être
  propagée aux autres postes.

`ALJ_CACHE_REPLICATION=off` keeps the cache local (no Firestore replication): the tests, and a local
server that must not touch Firestore's member data.
"""
import logging
import os
import socket
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Optional

# Re-exported: callers and tests use `cloud_database.<name>` as the public API of the package.
from infrastructure.firestore.cloud_sync.bootstrap import (  # noqa: F401
    build_cache,
    cache_is_valid,
    create_schema,
    export_rows,
    import_database,
)
from infrastructure.firestore.cloud_sync.cache import (  # noqa: F401
    connect,
    get_state,
    install_tracking,
    pending_count,
    set_state,
    table_columns,
    table_exists,
    table_pk,
    tracked_tables,
)
from infrastructure.firestore.cloud_sync.common import (  # noqa: F401
    BY_FIELD,
    CACHE_FORMAT,
    COLLECTION_PREFIX,
    COMMIT_CHUNK,
    DEFAULT_PROJECT_ID,
    DEL_FIELD,
    META_FIELDS,
    MOD_FIELD,
    PULL_MARGIN_SECONDS,
    REFERENCES,
    TRACKED_TABLES,
    CloudConflictError,
    CloudSyncError,
    collection_for,
    decode_value,
    doc_id_for,
    encode_value,
    quote_field_path,
    ts_key,
    ts_minus,
)
from infrastructure.firestore.cloud_sync.rest_store import RestStore
from infrastructure.firestore.cloud_sync.sync import apply_remote_docs, flush, pull, renumber_row  # noqa: F401

logger = logging.getLogger("alj")

REPLICATION_ENV = "ALJ_CACHE_REPLICATION"


class CloudDatabase:
    """Point d'entrée : synchronisation du cache `database.db` avec Firestore."""

    _lock = threading.RLock()
    _store = None
    _last_report: Dict[str, Any] = {}
    _last_error = ""
    _last_sync = 0.0
    _last_pull = 0.0
    _projection_dirty = False
    _last_projection = 0.0

    @staticmethod
    def is_enabled() -> bool:
        """Whether the cache is replicated with Firestore: always, unless ALJ_CACHE_REPLICATION=off (tests, local
        server kept away from Firestore's member data)."""
        return os.environ.get(REPLICATION_ENV, "").strip().lower() != "off"

    @classmethod
    def store(cls):
        if cls._store is None:
            cls._store = RestStore()
        return cls._store

    @staticmethod
    def db_path() -> str:
        from infrastructure.sqlite.connection import SqliteDatabase
        return SqliteDatabase.get_db_path()

    @staticmethod
    def who() -> str:
        try:
            return f"{os.environ.get('USERNAME') or os.environ.get('USER') or '?'}@{socket.gethostname()}"
        except Exception:
            return "?"

    @classmethod
    def sync(cls, full: bool = False, progress: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Met le cache à jour : reconstruction si besoin (toujours si `full`), puis réception et envoi."""
        with cls._lock:
            path = cls.db_path()
            store = cls.store()
            report: Dict[str, Any] = {}
            try:
                if full or not cache_is_valid(path, store.project_id):
                    if progress:
                        progress("Chargement complet de la base depuis Firestore…")
                    backup_dir = os.path.join(os.path.dirname(path), "backups")
                    report = build_cache(path, store, backup_dir=backup_dir)
                    from infrastructure.sqlite.connection import SqliteDatabase
                    SqliteDatabase._database_setup_done = False
                    SqliteDatabase.setup_database()
                    report["full"] = True
                conn = connect(path)
                try:
                    install_tracking(conn)  # after a rebuild too: the triggers of the new file
                    if progress:
                        progress("Réception des modifications Firestore…")
                    pull(conn, store, report)
                    if progress:
                        progress("Envoi des modifications locales…")
                    flush(conn, store, cls.who(), report)
                    try:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except sqlite3.DatabaseError:
                        pass
                finally:
                    conn.close()
                cls._after_sync(report)
                cls._last_pull = time.time()
                cls._last_error = ""
            except Exception as e:
                cls._last_error = str(e)
                report.setdefault("errors", []).append(str(e))
                print(f"❌ [CLOUD_DB] Synchronisation Firestore impossible : {e}")
            cls._last_report = report
            cls._last_sync = time.time()
            return report

    @classmethod
    def flush_only(cls) -> Dict[str, Any]:
        with cls._lock:
            path = cls.db_path()
            report: Dict[str, Any] = {}
            if not cache_is_valid(path, cls.store().project_id):
                return report
            conn = connect(path)
            try:
                if pending_count(conn):
                    flush(conn, cls.store(), cls.who(), report)
            except Exception as e:
                cls._last_error = str(e)
                report.setdefault("errors", []).append(str(e))
                print(f"❌ [CLOUD_DB] Envoi vers Firestore impossible : {e}")
            finally:
                conn.close()
            cls._after_sync(report)
            return report

    @classmethod
    def _after_sync(cls, report: Dict[str, Any]):
        if set(report.get("tables") or []) & {"users", "orders", "purchases", "planning", "seasons"}:
            cls._projection_dirty = True
        if report.get("pushed") or report.get("deleted") or report.get("pulled"):
            print(f"☁️ [CLOUD_DB] envoyés={report.get('pushed', 0)} supprimés={report.get('deleted', 0)} "
                  f"reçus={report.get('pulled', 0)} conflits={report.get('conflicts', 0)}")

    @classmethod
    def mark_projection_dirty(cls) -> None:
        """The `adherents` directory is rewritten by the next background tick (e.g. written before a field existed)."""
        cls._projection_dirty = True

    @classmethod
    def refresh_projection(cls, force: bool = False):
        """Met à jour l'annuaire `adherents` / `planning` lu par la PWA et le webhook."""
        if not (cls._projection_dirty or force):
            return
        try:
            from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository
            rep = CompetitionFirestoreRepository.sync_adherents_from_main()
            if not rep.get("errors"):
                cls._projection_dirty = False
            cls._last_projection = time.time()
        except Exception as e:
            print(f"⚠️ [CLOUD_DB] Mise à jour de l'annuaire Firestore impossible : {e}")

    @classmethod
    def status(cls) -> Dict[str, Any]:
        path = cls.db_path()
        pending = 0
        if os.path.exists(path):
            try:
                conn = connect(path)
                pending = pending_count(conn)
                conn.close()
            except Exception:
                logger.warning("Comptage des modifications en attente impossible", exc_info=True)
        return {"pending": pending, "last_error": cls._last_error, "last_sync": cls._last_sync}

    @classmethod
    def background_tick(cls, pull_every: int = 120, projection_every: int = 180):
        if not cls.is_enabled() or not cache_is_valid(cls.db_path(), cls.store().project_id):
            return
        try:
            if time.time() - cls._last_pull >= pull_every:
                cls.sync()
            else:
                cls.flush_only()
            if cls._projection_dirty and time.time() - cls._last_projection >= projection_every:
                cls.refresh_projection()
        except Exception as e:
            print(f"⚠️ [CLOUD_DB] Synchronisation d'arrière-plan : {e}")



    @classmethod
    def cache_ready(cls) -> bool:
        """Vrai si un cache local issu de Firestore est disponible (même hors ligne)."""
        path = cls.db_path()
        if not os.path.exists(path):
            return False
        try:
            conn = connect(path)
            try:
                return get_state(conn, "format") == CACHE_FORMAT
            finally:
                conn.close()
        except sqlite3.DatabaseError:
            return False

    @classmethod
    def ensure_fresh(cls, max_age: int = 30) -> None:
        """Serveur (Cloud Run) : construit le cache au premier appel, puis récupère
        les modifications si la dernière réception date de plus de `max_age` s."""
        if not cls.is_enabled():
            return
        if (not cache_is_valid(cls.db_path(), cls.store().project_id)
                or time.time() - cls._last_pull >= max_age):
            cls.sync()

    @classmethod
    def after_write(cls) -> None:
        """Envoie aussitôt les modifications locales (serveur) et met à jour
        l'annuaire `adherents` de la PWA si des adhérents / le planning ont changé."""
        if not cls.is_enabled():
            return
        cls.flush_only()
        cls.refresh_projection()
