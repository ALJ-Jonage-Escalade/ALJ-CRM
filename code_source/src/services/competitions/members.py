"""Members as seen by the competition pages (Firestore `adherents` projection, read-only).

The full member records are served by the member routes (plan phase 2), not here.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from services.competitions.store import storage
from services.documents import Doc


class CompetitionMemberService:

    @staticmethod
    @storage
    def list_members(statuses: Optional[Sequence[str]] = None) -> List[Doc]:
        """`statuses`: only the members at one of these membership statuses; None: every member."""
        return Repo.list_adherents(statuses=statuses)
