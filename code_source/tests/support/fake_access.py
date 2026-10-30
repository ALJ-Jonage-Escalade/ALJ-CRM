"""In-memory access list (Firestore access_roles / access_requests / access_history) and a settable clock.

tests/conftest.py installs one for every test: no test reads the real access list, and none has a role unless it
lists the address (`grant_roles`)."""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from infrastructure.firestore.access_store import AccessRequestEntry, HistoryEntry, RoleEntry
from infrastructure.security import role_directory
from infrastructure.security.role_directory import RoleDirectory

START = datetime.datetime(2026, 10, 30, 9, 0, tzinfo=datetime.timezone.utc)


class FakeClock:
    def __init__(self, now: datetime.datetime = START) -> None:
        self.now = now

    def __call__(self) -> datetime.datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += datetime.timedelta(**delta)


class StoreDown(RuntimeError):
    """Raised by every read of a failing store (Firestore unreachable)."""


class InMemoryAccessStore:
    def __init__(self) -> None:
        self.roles: Dict[str, RoleEntry] = {}
        self.requests: Dict[str, AccessRequestEntry] = {}
        self.history: List[HistoryEntry] = []
        self.failing = False
        self.role_reads = 0
        self.writes = 0

    def _check(self) -> None:
        if self.failing:
            raise StoreDown("Firestore injoignable")

    def list_roles(self) -> List[RoleEntry]:
        self._check()
        self.role_reads += 1
        return [RoleEntry(**entry) for entry in self.roles.values()]  # type: ignore[typeddict-item]

    def get_role(self, email: str) -> Optional[RoleEntry]:
        self._check()
        entry = self.roles.get(email)
        return RoleEntry(**entry) if entry else None  # type: ignore[typeddict-item]

    def create_role(self, entry: RoleEntry) -> bool:
        self._check()
        if entry["email"] in self.roles:
            return False
        self.writes += 1
        self.roles[entry["email"]] = RoleEntry(**entry)  # type: ignore[typeddict-item]
        return True

    def save_role(self, entry: RoleEntry) -> None:
        self._check()
        self.writes += 1
        self.roles[entry["email"]] = RoleEntry(**entry)  # type: ignore[typeddict-item]

    def update_role(self, email: str, fields: Dict[str, Any]) -> None:
        self._check()
        self.writes += 1
        self.roles[email] = RoleEntry(**{**self.roles[email], **fields})  # type: ignore[typeddict-item]

    def delete_role(self, email: str) -> None:
        self._check()
        self.writes += 1
        self.roles.pop(email, None)

    def list_requests(self) -> List[AccessRequestEntry]:
        self._check()
        return [AccessRequestEntry(**r) for r in self.requests.values()]  # type: ignore[typeddict-item]

    def get_request(self, email: str) -> Optional[AccessRequestEntry]:
        self._check()
        request = self.requests.get(email)
        return AccessRequestEntry(**request) if request else None  # type: ignore[typeddict-item]

    def save_request(self, entry: AccessRequestEntry) -> None:
        self._check()
        self.writes += 1
        self.requests[entry["email"]] = AccessRequestEntry(**entry)  # type: ignore[typeddict-item]

    def delete_request(self, email: str) -> None:
        self._check()
        self.writes += 1
        self.requests.pop(email, None)

    def add_history(self, entry: HistoryEntry) -> None:
        self._check()
        self.writes += 1
        self.history.append(HistoryEntry(**entry))  # type: ignore[typeddict-item]

    def list_history(self) -> List[HistoryEntry]:
        self._check()
        return list(self.history)


def role_entry(email: str, role: str, display_name: str = "") -> RoleEntry:
    return RoleEntry(email=email, role=role, display_name=display_name, last_sign_in_at=None,
                     created_at=None, created_by=None, updated_at=None, updated_by=None)


def install_access(store: Optional[InMemoryAccessStore] = None, clock: Optional[FakeClock] = None,
                   bootstrap_email: str = "") -> RoleDirectory:
    """Makes the server use this in-memory list (fresh one by default) through its role directory."""
    directory = RoleDirectory(store or InMemoryAccessStore(), clock or FakeClock(), bootstrap_email)
    role_directory.install(directory)
    return directory


def grant_roles(roles_by_email: Dict[str, str]) -> None:
    """Lists these addresses in the server's access list: grant_roles({"a@b.c": "coach"})."""
    directory = role_directory.current()
    for email, role in roles_by_email.items():
        directory.store.save_role(role_entry(email, role))
    directory.invalidate()
