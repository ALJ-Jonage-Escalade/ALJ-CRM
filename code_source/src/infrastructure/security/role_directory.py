"""Role of an e-mail address, read from the access list (Firestore `access_roles`): the only source of roles.

The whole list is kept in memory for CACHE_SECONDS: a change made on another server instance applies within that
time, and at once on the instance that made it (`invalidate()`).

The bootstrap address (`BOOTSTRAP_ADMIN_EMAIL`, set on the Cloud Run service) is the emergency access: admin while it
is not listed, and when the list cannot be read. Once listed (created at startup, services/access/bootstrap.py), its
listed role applies, so a change made on the page sticks.

An invitation not accepted in time (`invitation_expires_at` past) gives no role: the entry stays on the page, where an
admin resends or removes it (services/access/rules.py).

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
from infrastructure.security.secret_store import SecretStore
from infrastructure.timed_cache import TimedCache

logger = logging.getLogger("alj")

CACHE_SECONDS = 60
_CACHE_KEY = "access_roles"

Clock = Callable[[], datetime.datetime]


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def normalized_email(email: object) -> str:
    return str(email or "").strip().lower()


def parsed(value: Optional[str]) -> Optional[datetime.datetime]:
    """An ISO date of the store (UTC when it has no zone); None when empty or not a date."""
    if not value:
        return None
    try:
        at = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)


def invitation_expired(entry: RoleEntry, now: datetime.datetime) -> bool:
    """The entry is an invitation nobody accepted in time. An unreadable date counts as expired."""
    if not entry["invitation_expires_at"]:
        return False
    expires = parsed(entry["invitation_expires_at"])
    return expires is None or now >= expires


class AccessUnavailable(Exception):
    """The access list could not be read: no role can be answered (API: 503)."""


class RoleDirectory:

    def __init__(self, store: AccessStore, clock: Clock = utc_now, bootstrap_email: str = "",
                 cache_seconds: int = CACHE_SECONDS) -> None:
        self.store = store
        self.clock = clock
        self.bootstrap_email = normalized_email(bootstrap_email)
        self.cache: TimedCache[str, Dict[str, RoleEntry]] = TimedCache(cache_seconds, clock=lambda: self.clock().timestamp())

    def entries(self) -> Dict[str, RoleEntry]:
        """The access list by e-mail, at most CACHE_SECONDS old; AccessUnavailable when it cannot be read."""
        return self.cache.get_or_load(_CACHE_KEY, self._read_entries)

    def _read_entries(self) -> Dict[str, RoleEntry]:
        try:
            listed = self.store.list_roles()
        except Exception as e:  # Firestore down, token refused…: no stale list served past the cache time
            logger.warning("Liste des accès illisible : %s", e)
            raise AccessUnavailable("Liste des accès illisible") from e
        return {normalized_email(entry["email"]): entry for entry in listed}

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
        if entry is None or invitation_expired(entry, self.clock()):
            return Role.ADMIN if self.bootstrap_email and email == self.bootstrap_email else None
        return role_named(entry["role"])

    def expired_invitation_of(self, email: str) -> Optional[str]:
        """When this address was invited but did not sign in in time: the end date of its invitation; None otherwise."""
        entry = self.entries().get(normalized_email(email))
        if entry is None or not invitation_expired(entry, self.clock()):
            return None
        return entry["invitation_expires_at"]

    def invalidate(self) -> None:
        """Drops the cached list: the next question reads it again."""
        self.cache.invalidate()


_current: Optional[RoleDirectory] = None
_current_lock = threading.Lock()


def current() -> RoleDirectory:
    """The server's directory, on Firestore (created on first use)."""
    global _current
    with _current_lock:
        if _current is None:
            # Dev mode: no cache, a seed or an edit in the emulator UI applies at once (the emulator is local and cheap)
            _current = RoleDirectory(FirestoreAccessStore(), bootstrap_email=SecretStore.get_secret("BOOTSTRAP_ADMIN_EMAIL"),
                                     cache_seconds=0 if runtime_env.is_dev() else CACHE_SECONDS)
        return _current


def install(directory: Optional[RoleDirectory]) -> None:
    """Replaces the server's directory (tests: an in-memory store); None: back to Firestore on next use."""
    global _current
    with _current_lock:
        _current = directory
