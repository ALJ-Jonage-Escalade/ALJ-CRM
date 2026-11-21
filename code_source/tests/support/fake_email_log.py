"""In-memory e-mail log: tests/conftest.py installs one for every test, so no send writes to the real Firestore."""

from __future__ import annotations

from typing import List

from domain.email_log import EmailKind, EmailLogEntry


class LogDown(RuntimeError):
    """Raised by a failing store (Firestore unreachable)."""


class InMemoryEmailLogStore:
    def __init__(self) -> None:
        self.entries: List[EmailLogEntry] = []
        self.failing = False

    def add_entry(self, entry: EmailLogEntry) -> None:
        if self.failing:
            raise LogDown("Firestore injoignable")
        self.entries.append(entry)

    def list_for_competition(self, competition_id: int) -> List[EmailLogEntry]:
        if self.failing:
            raise LogDown("Firestore injoignable")
        return [entry for entry in self.entries if competition_id in entry["competition_ids"]]

    def list_latest(self, limit: int) -> List[EmailLogEntry]:
        if self.failing:
            raise LogDown("Firestore injoignable")
        return sorted(self.entries, key=lambda entry: entry["at"], reverse=True)[:limit]

    def list_of_kind(self, kind: EmailKind) -> List[EmailLogEntry]:
        if self.failing:
            raise LogDown("Firestore injoignable")
        return [entry for entry in self.entries if entry["kind"] == kind]
