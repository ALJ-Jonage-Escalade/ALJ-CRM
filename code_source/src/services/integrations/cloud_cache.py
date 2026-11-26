"""The SQLite cache of the crm_* Firestore collections: its state and a forced sync (Paramètres page)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.sqlite.members import MemberRepository

logger = logging.getLogger("alj")


@dataclass(frozen=True)
class CacheStatus:
    """last_sync: Unix time of the last sync, 0 or None before the first one; last_sync_failed: its error is in the
    logs only (Firestore and SQLite texts never reach the page)."""
    enabled: bool
    db_exists: bool
    db_filename: str
    db_size_kb: float
    member_count: int
    pending: int
    last_sync_failed: bool
    last_sync: Optional[float]


@dataclass(frozen=True)
class CacheSync:
    """Counters of a forced sync; error_count > 0 when part of it failed (details logged)."""
    pulled: int
    pushed: int
    full: bool
    error_count: int


def cache_status() -> CacheStatus:
    enabled = CloudDatabase.is_enabled()
    replication = CloudDatabase.status() if enabled else {}
    db_path = SqliteDatabase.get_db_path()
    db_exists = os.path.exists(db_path)

    member_count = 0
    if db_exists:
        try:
            member_count = MemberRepository.count_members()
        except Exception:  # the page shows 0: the count is informative only
            logger.warning("Lecture du nombre d'adhérents du cache SQLite impossible", exc_info=True)

    return CacheStatus(
        enabled=enabled,
        db_exists=db_exists,
        db_filename=os.path.basename(db_path),
        db_size_kb=round(os.path.getsize(db_path) / 1024, 1) if db_exists else 0,
        member_count=member_count,
        pending=replication.get("pending", 0),
        last_sync_failed=bool(replication.get("last_error")),
        last_sync=replication.get("last_sync"),
    )


def sync_cache(full: bool) -> Optional[CacheSync]:
    """Pulls then pushes the cache's changes (a full rebuild when `full`); None when replication is off."""
    if not CloudDatabase.is_enabled():
        return None
    report = CloudDatabase.sync(full=full)
    errors = report.get("errors") or []
    for err in errors:
        logger.warning(f"[CLOUD_DB] Synchronisation : {err}")
    return CacheSync(pulled=report.get("pulled", 0), pushed=report.get("pushed", 0), full=report.get("full", False),
                     error_count=len(errors))
