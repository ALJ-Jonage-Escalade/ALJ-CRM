"""Members as seen by the competition pages (Firestore `adherents` projection, read-only).

The full member records are served by the member routes (plan phase 2), not here.
"""

from __future__ import annotations

from typing import List

from infrastructure.competition_firestore_repository import CompetitionFirestoreRepository as Repo
from services.competition_store import storage
from services.documents import Doc


class CompetitionMemberService:

    @staticmethod
    @storage
    def list_members() -> List[Doc]:
        return Repo.list_adherents()
