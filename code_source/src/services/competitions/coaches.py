"""Coaches. A rename or a delete also updates the competitions the coach is on.

Knows nothing about HTTP: failures are raised as domain.errors.
"""

from __future__ import annotations

from typing import List

from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from services.competitions.store import storage, write
from domain.errors import NotFound


def _require_coach(coach_id: int) -> None:
    if Repo.get_coach(coach_id) is None:
        raise NotFound("Coach introuvable.")


class CoachService:

    @staticmethod
    @storage
    def list_coaches() -> List[dict]:
        return Repo.list_coaches()

    @staticmethod
    @write
    def create_coach(nom: str) -> int:
        return Repo.save_coach(nom)

    @staticmethod
    @write
    def rename_coach(coach_id: int, nom: str) -> None:
        """Renames the coach and the name copied into their competitions."""
        _require_coach(coach_id)
        Repo.save_coach(nom, coach_id)

    @staticmethod
    @write
    def delete_coach(coach_id: int) -> None:
        """Deletes the coach and removes them from every competition."""
        _require_coach(coach_id)
        Repo.delete_coach(coach_id)
