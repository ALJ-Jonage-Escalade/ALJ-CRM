"""Changes to the access list (Administration › Accès) and the sign-ins that feed it.

Every change goes through here: it enforces the safeguards (no admin removes or demotes themselves, the list always
keeps an admin), writes exactly one history entry and drops the role cache of this instance, so the change applies
at once here and within a minute on the others (role_directory.CACHE_SECONDS).

Sign-ins (GET /api/me) record the last sign-in date of a listed person, or an access request for an unknown one,
at most once a day per address and instance: /api/me is called on every page load.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Dict, List, Optional

from domain.validators import validate_email
from infrastructure import runtime_env
from infrastructure.firestore.access_store import AccessRequestEntry, AccessStore, HistoryEntry, RoleEntry
from infrastructure.security import role_directory
from infrastructure.security.role_directory import Clock, RoleDirectory, normalized_email
from infrastructure.security.roles import ROLES_BY_NAME, RoleName
from services.errors import Conflict, InvalidRequest, NotFound

logger = logging.getLogger("alj")

# A dismissed address is not recorded again for this long; a request nobody answered is dropped after it
REQUEST_DAYS = 30
HISTORY_LIMIT = 50
DISPLAY_NAME_MAX = 100
BOOTSTRAP_AUTHOR = "bootstrap"


def iso(at: datetime.datetime) -> str:
    return at.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def parsed(value: Optional[str]) -> Optional[datetime.datetime]:
    if not value:
        return None
    try:
        at = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=datetime.timezone.utc)


def checked_email(email: object) -> str:
    """The address trimmed and in lower case; InvalidRequest when it is empty or malformed."""
    try:
        clean = validate_email(email)
    except ValueError as e:
        raise InvalidRequest(str(e), "invalid_email") from e
    if not clean:
        raise InvalidRequest("Adresse e-mail obligatoire.", "invalid_email")
    return clean


def checked_role(role: str) -> RoleName:
    if role not in ROLES_BY_NAME:
        raise InvalidRequest(f"Rôle inconnu : « {role} ».", "invalid_role")
    return role  # type: ignore[return-value]  # checked against the role names just above


def clean_display_name(name: object) -> str:
    return " ".join(str(name or "").split())[:DISPLAY_NAME_MAX]


class AccessRules:

    def __init__(self, store: AccessStore, directory: RoleDirectory, clock: Clock, remember_days: bool = True) -> None:
        self.store = store
        self.directory = directory
        self.clock = clock
        # Day of the last write per address on this instance: /api/me writes at most once a day per person, without
        # reading the store again. Off in dev mode, where a re-seed empties the store under a running server.
        self._remember_days = remember_days
        self._sign_in_days: Dict[str, datetime.date] = {}
        self._request_days: Dict[str, datetime.date] = {}

    # ------------------------------------------------------------------ Reads
    def list_roles(self) -> List[RoleEntry]:
        return sorted(self.store.list_roles(), key=lambda entry: entry["email"])

    def entry_of(self, email: str) -> RoleEntry:
        """The entry of this address; NotFound when it has no access."""
        entry = self.store.get_role(normalized_email(email))
        if entry is None:
            raise NotFound(f"Aucun accès pour {normalized_email(email)}.", "not_listed")
        return entry

    def list_requests(self) -> List[AccessRequestEntry]:
        """Pending requests, latest first. Requests nobody answered for REQUEST_DAYS, and dismissals older than that,
        are deleted here."""
        now = self.clock()
        pending: List[AccessRequestEntry] = []
        for request in self.store.list_requests():
            dismissed = parsed(request["dismissed_at"])
            last = parsed(request["last_requested_at"]) or parsed(request["first_requested_at"])
            if dismissed is not None:
                if self._expired(dismissed, now):
                    self.store.delete_request(request["email"])
                continue
            if last is None or self._expired(last, now):
                self.store.delete_request(request["email"])
                continue
            pending.append(request)
        return sorted(pending, key=lambda request: request["last_requested_at"], reverse=True)

    def history(self, limit: int = HISTORY_LIMIT) -> List[HistoryEntry]:
        """The latest changes, latest first: only those are read."""
        return self.store.list_history(limit)

    # ------------------------------------------------------------------ Changes
    def grant(self, author: str, email: str, role: str, display_name: str = "") -> RoleEntry:
        """Gives access to a new address; refused when it already has one."""
        return self._create(author, checked_email(email), checked_role(role), display_name, "added")

    def change_role(self, author: str, email: str, role: str) -> RoleEntry:
        entry = self.entry_of(email)
        new_role = checked_role(role)
        if entry["role"] == new_role:
            return entry
        if self._is_self(author, entry) and new_role != "admin":
            raise Conflict("Vous ne pouvez pas retirer votre propre rôle d'administrateur.", "self_demotion")
        if entry["role"] == "admin":
            self._keep_an_admin(entry, "Impossible de retirer le rôle d'administrateur : c'est le dernier administrateur de la liste.")
        changed = self._updated(author, entry, role=new_role)
        self._history(author, "role_changed", entry["email"], entry["role"], new_role)
        return changed

    def rename(self, author: str, email: str, display_name: str) -> RoleEntry:
        entry = self.entry_of(email)
        name = clean_display_name(display_name)
        if entry["display_name"] == name:
            return entry
        changed = self._updated(author, entry, display_name=name)
        self._history(author, "name_changed", entry["email"], entry["role"], entry["role"])
        return changed

    def remove(self, author: str, email: str) -> None:
        entry = self.entry_of(email)
        if self._is_self(author, entry):
            raise Conflict("Vous ne pouvez pas retirer votre propre accès.", "self_removal")
        if entry["role"] == "admin":
            self._keep_an_admin(entry, "Impossible de retirer cet accès : c'est le dernier administrateur de la liste.")
        self.store.delete_role(entry["email"])
        self._history(author, "removed", entry["email"], entry["role"], None)
        self.directory.invalidate()

    def grant_request(self, author: str, email: str, role: str, display_name: Optional[str] = None) -> RoleEntry:
        """Gives access to a pending request: the request becomes an entry of the list."""
        request = self._pending_request(email)
        name = request["google_display_name"] if display_name is None else display_name
        return self._create(author, request["email"], checked_role(role), name, "request_granted")

    def dismiss_request(self, author: str, email: str) -> None:
        """The request leaves the list; the address is not recorded again for REQUEST_DAYS."""
        request = self._pending_request(email)
        self.store.save_request({**request, "dismissed_at": iso(self.clock())})
        self._history(author, "request_dismissed", request["email"], None, None)

    # ------------------------------------------------------------------ Sign-ins (GET /api/me)
    def record_sign_in(self, email: str) -> None:
        """Last sign-in date of a listed person, written at most once a day."""
        email = normalized_email(email)
        now = self.clock()
        today = now.date()
        if not email or self._remembered(self._sign_in_days, email, today):
            return
        entry = self.directory.entries().get(email)
        if entry is None:
            return  # the bootstrap address before its entry is created
        last = parsed(entry["last_sign_in_at"])
        if last is None or last.date() != today:
            self.store.update_role(email, {"last_sign_in_at": iso(now)})
        self._sign_in_days[email] = today

    def record_refused_sign_in(self, email: str, google_display_name: str = "") -> None:
        """An access request for a verified address without access: one per address, updated on a new sign-in, not
        recorded while dismissed less than REQUEST_DAYS ago."""
        try:
            email = checked_email(email)
        except InvalidRequest:
            return
        now = self.clock()
        today = now.date()
        if self._remembered(self._request_days, email, today):
            return
        request = self.store.get_request(email)
        self._request_days[email] = today
        if request is not None:
            dismissed = parsed(request["dismissed_at"])
            if dismissed is not None and not self._expired(dismissed, now):
                return
            last = parsed(request["last_requested_at"])
            if dismissed is None and last is not None and not self._expired(last, now):
                self.store.save_request({**request, "last_requested_at": iso(now),
                                         "google_display_name": clean_display_name(google_display_name)
                                         or request["google_display_name"]})
                return
        self.store.save_request(AccessRequestEntry(
            email=email, google_display_name=clean_display_name(google_display_name),
            first_requested_at=iso(now), last_requested_at=iso(now), dismissed_at=None))

    # ------------------------------------------------------------------ Helpers
    def _create(self, author: str, email: str, role: RoleName, display_name: str, action: str) -> RoleEntry:
        at = iso(self.clock())
        entry = RoleEntry(email=email, role=role, display_name=clean_display_name(display_name), last_sign_in_at=None,
                          created_at=at, created_by=author, updated_at=at, updated_by=author)
        if not self.store.create_role(entry):
            raise Conflict(f"{email} a déjà un accès.", "already_listed")
        if self.store.get_request(email) is not None:
            self.store.delete_request(email)  # the person now has access
        self._request_days.pop(email, None)
        self._history(author, action, email, None, role)
        self.directory.invalidate()
        return entry

    def _pending_request(self, email: str) -> AccessRequestEntry:
        email = normalized_email(email)
        request = next((r for r in self.list_requests() if r["email"] == email), None)
        if request is None:
            raise NotFound(f"Aucune demande d'accès en attente pour {email}.", "no_request")
        return request

    def _updated(self, author: str, entry: RoleEntry, **fields: str) -> RoleEntry:
        fields = {**fields, "updated_at": iso(self.clock()), "updated_by": author}
        self.store.update_role(entry["email"], fields)
        self.directory.invalidate()
        return RoleEntry(**{**entry, **fields})  # type: ignore[typeddict-item]  # fields are RoleEntry keys

    def _keep_an_admin(self, entry: RoleEntry, message: str) -> None:
        admins = [other for other in self.store.list_roles() if other["role"] == "admin"]
        if all(normalized_email(other["email"]) == entry["email"] for other in admins):
            raise Conflict(message, "last_admin")

    def _history(self, author: str, action: str, email: str, old_role: Optional[str], new_role: Optional[str]) -> None:
        self.store.add_history(HistoryEntry(at=iso(self.clock()), author=author, action=action, target_email=email,
                                            old_role=old_role, new_role=new_role))

    def _remembered(self, days: Dict[str, datetime.date], email: str, today: datetime.date) -> bool:
        return self._remember_days and days.get(email) == today

    @staticmethod
    def _is_self(author: str, entry: RoleEntry) -> bool:
        return normalized_email(author) == entry["email"]

    @staticmethod
    def _expired(at: datetime.datetime, now: datetime.datetime) -> bool:
        return now - at >= datetime.timedelta(days=REQUEST_DAYS)


_current: Optional[AccessRules] = None
_current_lock = threading.Lock()


def current() -> AccessRules:
    """The server's rules, on the store and cache of the server's role directory."""
    global _current
    with _current_lock:
        directory = role_directory.current()
        if _current is None or _current.directory is not directory:
            _current = AccessRules(directory.store, directory, directory.clock, remember_days=not runtime_env.is_dev())
        return _current
