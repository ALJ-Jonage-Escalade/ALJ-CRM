"""Competitions: list, create, partial update, delete, archive.

Over CompetitionFirestoreRepository (shared with the desktop app and the HelloAsso
webhook, so all three write with the same rules). Knows nothing about HTTP: failures are
raised as services.errors.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List

from domain.competitions.models import Competition
from infrastructure.firestore.competition_repository import CompetitionFirestoreRepository as Repo
from services.competitions.store import cached_competitions, competition_not_found, require_competition, storage, write
from services.documents import Doc

# Fields stored as given, outside the domain model (plan appendix B)
PASS_THROUGH_FIELDS = ("lieu", "type")
COMPETITION_FIELDS = ("nom", "id_ffme", "date_competition", "date_fin", "prix", "statut",
                      "helloasso_ref", "url_resultats", "whatsapp_link")


def _extra(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {k: fields[k] for k in PASS_THROUGH_FIELDS if k in fields}


class CompetitionService:

    @staticmethod
    @storage
    def list_competitions() -> List[Doc]:
        return cached_competitions(Repo.list_competition_docs)

    @staticmethod
    @write
    def create_competition(fields: Dict[str, Any]) -> Doc:
        """`fields`: validated body (api.competitions.schemas.competitions.CompetitionCreate)."""
        comp = Competition(**{k: fields[k] for k in COMPETITION_FIELDS if k in fields})
        comp.coach_ids = list(fields.get("coach_ids") or [])
        new_id = Repo.save_competition(comp, _extra(fields))
        return require_competition(new_id)

    @staticmethod
    @write
    def update_competition(competition_id: int, fields: Dict[str, Any]) -> Doc:
        """Partial update: only the fields given are changed (participants untouched), on the
        version of the document read (a concurrent write to other fields is kept)."""
        def change(comp: Competition) -> None:
            for field in COMPETITION_FIELDS:
                if fields.get(field) is not None:
                    setattr(comp, field, fields[field])
            if "coach_ids" in fields:
                comp.coach_ids = list(fields["coach_ids"] or [])
        if not Repo.update_competition(competition_id, change, _extra(fields)):
            raise competition_not_found()
        return require_competition(competition_id)

    @staticmethod
    @write
    def delete_competition(competition_id: int) -> None:
        if not Repo.delete_competition(competition_id):
            raise competition_not_found()

    @staticmethod
    @write
    def archive_past_competitions() -> List[int]:
        """Closes the competitions that are over; returns their ids."""
        return Repo.archive_past_competitions(datetime.date.today().isoformat())
