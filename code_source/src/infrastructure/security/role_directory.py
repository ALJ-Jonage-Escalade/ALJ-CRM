"""Role of an e-mail address, read from the access list (Firestore `access_roles`): the only source of roles.

The whole list is kept in memory for CACHE_SECONDS: a change made on another server instance applies within that
time, and at once on the instance that made it (`invalidate()`).

The bootstrap address (`BOOTSTRAP_ADMIN_EMAIL`, set on the Cloud Run service) is the emergency access: admin while it
is not listed, and when the list cannot be read. Once listed (created at startup, services/access/bootstrap.py), its
listed role applies, so a change made on the page sticks.

When the list cannot be read and the cache has expired, every other address gets AccessUnavailable, which the API
answers with 503 (never 403): the pages keep their "role could not be checked" state and the copy kept on the device.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Callable, Dict, Optional

from infrastructure import runtime_env
from infrastructure.firestore.access_store import AccessStore, FirestoreAccessStore, RoleEntry
from infrastructure.security.roles import Role, role_named

logger = logging.getLogger("alj")

CACHE_SECONDS = 60

Clock = Callable[[], datetime.datetime]


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def normalized_email(email: object) -> str:
    return str(email or "").strip().lower()


class AccessUnavailable(Exception):
    """The access list could not be read: no role can be answered (API: 503)."""


class RoleDirectory:

    def __init__(self, store: AccessStore, clock: Clock = utc_now, bootstrap_email: str = "",
                 cache_seconds: int = CACHE_SECONDS) -> None:
        self.store = store
        self.clock = clock
        self.bootstrap_email = normalized_email(bootstrap_email)
        self._cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._entries: Optional[Dict[str, RoleEntry]] = None
        self._loaded_at: Optional[datetime.datetime] = None

    def entries(self) -> Dict[str, RoleEntry]:
        """The access list by e-mail, at most CACHE_SECONDS old; AccessUnavailable when it cannot be read."""
        with self._lock:
            now = self.clock()
            fresh = self._loaded_at is not None and (now - self._loaded_at).total_seconds() < self._cache_seconds
            if self._entries is None or not fresh:
                try:
                    listed = self.store.list_roles()
                except Exception as e:  # Firestore down, token refused…: no stale list served past the cache time
                    logger.warning("Liste des accès illisible : %s", e)
                    raise AccessUnavailable("Liste des accès illisible") from e
                self._entries = {normalized_email(entry["email"]): entry for entry in listed}
                self._loaded_at = now
            return self._entries

    def role_of(self, email: str) -> Optional[Role]:
        """Role of this address, or None when it has no access."""
        email = normalized_email(email)
        if not email:
            return None
        try:
            entries = self.entries()
        except AccessUnavailable:
            if self.bootstrap_email and email == self.bootstrap_email:
                return Role.ADMIN
            raise
        entry = entries.get(email)
        if entry is None:
            return Role.ADMIN if self.bootstrap_email and email == self.bootstrap_email else None
        return role_named(entry["role"])

    def invalidate(self) -> None:
        """Drops the cached list: the next question reads it again."""
        with self._lock:
            self._entries = None
            self._loaded_at = None


_current: Optional[RoleDirectory] = None
_current_lock = threading.Lock()


def current() -> RoleDirectory:
    """The server's directory, on Firestore (created on first use)."""
    global _current
    with _current_lock:
        if _current is None:
            from infrastructure.security.secret_store import SecretStore
            # Dev mode: no cache, a seed or an edit in the emulator UI applies at once (the emulator is local and cheap)
            _current = RoleDirectory(FirestoreAccessStore(), bootstrap_email=SecretStore.get_secret("BOOTSTRAP_ADMIN_EMAIL"),
                                     cache_seconds=0 if runtime_env.is_dev() else CACHE_SECONDS)
        return _current


def install(directory: Optional[RoleDirectory]) -> None:
    """Replaces the server's directory (tests: an in-memory store); None: back to Firestore on next use."""
    global _current
    with _current_lock:
        _current = directory
