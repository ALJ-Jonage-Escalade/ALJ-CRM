"""Changes to the access list (Administration › Accès) and the sign-ins that feed it.

Every change goes through here: it enforces the safeguards (no admin removes or demotes themselves, the list always
keeps an admin), writes exactly one history entry and drops the role cache of this instance, so the change applies
at once here and within a minute on the others (role_directory.CACHE_SECONDS).

Access is by invitation only: an admin invites an address with a role, and the person gets it by signing in with a
Google account of that address within INVITATION_DAYS (role_directory: an expired invitation gives no role). The
invitation e-mail is only a convenience, sent by services/access/invitations.py.

Sign-ins (GET /api/me) accept a pending invitation (on every call until the write succeeds) and record the last
sign-in date, at most once a day per address and instance: /api/me is called on every page load. An address without
access leaves nothing.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import Dict, List, Optional

from domain.validators import validate_email
from infrastructure import runtime_env
from infrastructure.firestore.access_store import AccessStore, HistoryAction, HistoryEntry, RoleEntry
from infrastructure.security import role_directory
from infrastructure.security.role_directory import Clock, RoleDirectory, invitation_expired, normalized_email, parsed
from infrastructure.security.roles import ADMIN, RoleName, is_role_name
from domain.errors import Conflict, InvalidRequest, NotFound

logger = logging.getLogger("alj")

# An invitation not accepted within this time gives no role until an admin resends it
INVITATION_DAYS = 7
HISTORY_LIMIT = 50
DISPLAY_NAME_MAX = 100
BOOTSTRAP_AUTHOR = "bootstrap"


def iso(at: datetime.datetime) -> str:
    return at.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


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
    if not is_role_name(role):
        raise InvalidRequest(f"Rôle inconnu : « {role} ».", "invalid_role")
    return role


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

    # ------------------------------------------------------------------ Reads
    def list_roles(self) -> List[RoleEntry]:
        return sorted(self.store.list_roles(), key=lambda entry: entry["email"])

    def entry_of(self, email: str) -> RoleEntry:
        """The entry of this address; NotFound when it has no access."""
        entry = self.store.get_role(normalized_email(email))
        if entry is None:
            raise NotFound(f"Aucun accès pour {normalized_email(email)}.", "not_listed")
        return entry

    def history(self, limit: int = HISTORY_LIMIT) -> List[HistoryEntry]:
        """The latest changes, latest first: only those are read."""
        return self.store.list_history(limit)

    # ------------------------------------------------------------------ Changes
    def invite(self, author: str, email: str, role: str, display_name: str = "") -> RoleEntry:
        """Invites a new address for INVITATION_DAYS; refused when it is already listed. The e-mail is not sent here
        (`mark_invitation_sent` once it is)."""
        address = checked_email(email)
        new_role = checked_role(role)
        now = self.clock()
        at = iso(now)
        entry = RoleEntry(email=address, role=new_role, display_name=clean_display_name(display_name), last_sign_in_at=None,
                          created_at=at, created_by=author, updated_at=at, updated_by=author, invited_at=at,
                          invitation_expires_at=iso(now + datetime.timedelta(days=INVITATION_DAYS)),
                          invitation_sent_at=None, accepted_at=None)
        if not self.store.create_role(entry):
            existing = self.store.get_role(address)
            if existing is not None and existing["invitation_expires_at"]:
                raise Conflict(f"{address} a déjà une invitation : utilisez « Renvoyer » pour l'envoyer à nouveau.",
                               "already_invited")
            raise Conflict(f"{address} a déjà un accès.", "already_listed")
        self._history(author, "invited", address, None, new_role)
        self.directory.invalidate()
        return entry

    def renew_invitation(self, author: str, email: str) -> RoleEntry:
        """A pending or expired invitation gets INVITATION_DAYS again (before its e-mail is sent again); refused for
        an accepted invitation or an entry added before invitations."""
        entry = self.entry_of(email)
        if not entry["invitation_expires_at"]:
            raise Conflict(f"{entry['email']} a déjà accepté son accès : rien à renvoyer.", "not_invited")
        now = self.clock()
        changed = self._updated(author, entry, invited_at=iso(now),
                                invitation_expires_at=iso(now + datetime.timedelta(days=INVITATION_DAYS)),
                                invitation_sent_at=None)
        self._history(author, "invitation_resent", entry["email"], entry["role"], entry["role"])
        return changed

    def mark_invitation_sent(self, email: str) -> RoleEntry:
        """The invitation e-mail of this entry went out (no history entry: the invitation already has one)."""
        entry = self.entry_of(email)
        fields = {"invitation_sent_at": iso(self.clock())}
        self.store.update_role(entry["email"], fields)
        self.directory.invalidate()
        return RoleEntry(**{**entry, **fields})  # type: ignore[typeddict-item]  # fields are RoleEntry keys

    def change_role(self, author: str, email: str, role: str) -> RoleEntry:
        entry = self.entry_of(email)
        new_role = checked_role(role)
        if entry["role"] == new_role:
            return entry
        if self._is_self(author, entry) and new_role != ADMIN:
            raise Conflict("Vous ne pouvez pas retirer votre propre rôle d'administrateur.", "self_demotion")
        if entry["role"] == ADMIN:
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
        if entry["role"] == ADMIN:
            self._keep_an_admin(entry, "Impossible de retirer cet accès : c'est le dernier administrateur de la liste.")
        self.store.delete_role(entry["email"])
        self._history(author, "removed", entry["email"], entry["role"], None)
        self.directory.invalidate()

    # ------------------------------------------------------------------ Sign-ins (GET /api/me)
    def accept_invitation(self, email: str) -> None:
        """A person with a role signed in: their pending invitation becomes an accepted one. Checked on every sign-in
        (not once a day), so a failed write is tried again on the next one."""
        email = normalized_email(email)
        cached = self.directory.entries().get(email)
        if cached is None or not cached["invitation_expires_at"]:
            return
        entry = self.store.get_role(email)  # read again: the cache may still hold an entry removed meanwhile
        if entry is None or not entry["invitation_expires_at"] or invitation_expired(entry, self.clock()):
            self.directory.invalidate()
            return
        self.store.update_role(email, {"invitation_expires_at": None, "accepted_at": iso(self.clock())})
        self.directory.invalidate()

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

    # ------------------------------------------------------------------ Helpers
    def _updated(self, author: str, entry: RoleEntry, **fields: Optional[str]) -> RoleEntry:
        fields = {**fields, "updated_at": iso(self.clock()), "updated_by": author}
        self.store.update_role(entry["email"], fields)
        self.directory.invalidate()
        return RoleEntry(**{**entry, **fields})  # type: ignore[typeddict-item]  # fields are RoleEntry keys

    def _keep_an_admin(self, entry: RoleEntry, message: str) -> None:
        admins = [other for other in self.store.list_roles() if other["role"] == ADMIN]
        if all(normalized_email(other["email"]) == entry["email"] for other in admins):
            raise Conflict(message, "last_admin")

    def _history(self, author: str, action: HistoryAction, email: str, old_role: Optional[str], new_role: Optional[str]) -> None:
        self.store.add_history(HistoryEntry(at=iso(self.clock()), author=author, action=action, target_email=email,
                                            old_role=old_role, new_role=new_role))

    def _remembered(self, days: Dict[str, datetime.date], email: str, today: datetime.date) -> bool:
        return self._remember_days and days.get(email) == today

    @staticmethod
    def _is_self(author: str, entry: RoleEntry) -> bool:
        return normalized_email(author) == entry["email"]


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
