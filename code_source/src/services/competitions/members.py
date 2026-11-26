"""Members as seen by the competition pages (Firestore `adherents` projection, read-only).

The full member records are served by the member routes, not here.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from infrastructure.firestore.competitions import member_directory
from services.competitions.store import storage
from services.json_types import Doc


class CompetitionMemberService:

    @staticmethod
    @storage
    def list_members(statuses: Optional[Sequence[str]] = None) -> List[Doc]:
        """`statuses`: only the members at one of these membership statuses; None: every member."""
        return member_directory.list_members(statuses=statuses)
