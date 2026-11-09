"""Participants of a competition (array embedded in the competition document).

Every write goes through the repository's optimistic lock (re-read and retried on a
concurrent change). Knows nothing about HTTP: failures are raised as domain.errors.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from domain.competitions.models import STATUT_CLOSE
from infrastructure.firestore.competitions import competitions
from infrastructure.firestore.competition_repository import (
    CompetitionRepository,
    ParticipantAlreadyPaid,
    ParticipantChanged,
)
from services.competitions.store import require_competition, write
from domain.errors import Conflict, NotFound


def _written(competition_id: int, doc: Optional[dict]) -> dict:
    """The competition as the write left it. `doc` None (nothing written): the competition is
    read, which also raises NotFound when it does not exist."""
    return competitions.competition_api_doc(doc) if doc is not None else require_competition(competition_id)


def _require_open(competition_id: int) -> None:
    """Changes queued offline are refused on an archived competition (Conflict
    `competition_closed`); online changes keep working there."""
    if require_competition(competition_id).get("statut") == STATUT_CLOSE:
        raise Conflict("Compétition archivée : modification refusée.", "competition_closed")


def _participant_not_found(competition_id: int) -> NotFound:
    require_competition(competition_id)  # unknown competition: its own message
    return NotFound("Compétiteur absent de cette compétition.")


class ParticipantService:
    """Each write answers with the document it wrote: one read of the competition (inside
    the write) instead of an existence check before and a read after."""

    @staticmethod
    @write
    def add_participant(competition_id: int, adherent_id: int, selectionne: bool) -> dict:
        return _written(competition_id, CompetitionRepository.add_participant_doc(competition_id, adherent_id, selectionne))

    @staticmethod
    @write
    def update_participant(competition_id: int, adherent_id: int,
                           selectionne: Optional[bool] = None,
                           present: Optional[bool] = None,
                           unchanged_since: Optional[str] = None) -> dict:
        """Unselecting a participant who paid is refused (Conflict `already_paid`): the
        coach must then choose whether the money is lost or carried over (cancel_participant).

        `unchanged_since`: the participant's `updated_at` the client saw, sent with a change
        queued on a phone while offline, one flag at a time. The change is
        refused when the participant changed meanwhile (Conflict `changed`), on an archived
        competition (`competition_closed`), or when the member is no longer listed
        (NotFound); a flag already at the new value is accepted without a write."""
        queued = unchanged_since is not None
        if queued:
            _require_open(competition_id)
        doc = None
        try:
            if selectionne is not None:
                doc = CompetitionRepository.set_selection_doc(competition_id, adherent_id, selectionne, refuse_unselect_paid=True,
                                             unchanged_since=unchanged_since)
            if present is not None:
                doc = CompetitionRepository.set_present_doc(competition_id, adherent_id, present, unchanged_since=unchanged_since)
                if doc is None and not queued:
                    raise _participant_not_found(competition_id)
        except ParticipantAlreadyPaid as e:
            raise Conflict("Ce compétiteur a déjà payé : choisissez le sort de son paiement.",
                           "already_paid") from e
        except ParticipantChanged as e:
            raise Conflict("Modifié entre-temps sur un autre appareil : modification refusée.", "changed") from e
        written = _written(competition_id, doc)
        if queued and not any(p.get("adherent_id") == adherent_id for p in written.get("participants") or []):
            raise _participant_not_found(competition_id)
        return written

    @staticmethod
    @write
    def record_manual_payment(competition_id: int, adherent_id: int, montant: float) -> dict:
        """Cheque or cash: the participant becomes selected and paid."""
        doc = CompetitionRepository.record_manual_payment_doc(competition_id, adherent_id, montant)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return competitions.competition_api_doc(doc)

    @staticmethod
    @write
    def cancel_participant(competition_id: int, adherent_id: int, payment_status: str,
                           note: str) -> dict:
        """`payment_status`: PAIEMENT_ANNULE_PERDU or PAIEMENT_ANNULE_REPORTE."""
        doc = CompetitionRepository.mark_cancelled_doc(competition_id, adherent_id, payment_status, note)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return competitions.competition_api_doc(doc)

    @staticmethod
    @write
    def remove_participant(competition_id: int, adherent_id: int) -> dict:
        doc = CompetitionRepository.remove_participant_doc(competition_id, adherent_id)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return competitions.competition_api_doc(doc)

    @staticmethod
    @write
    def load_competition_group(competition_id: int, statuses: Optional[Sequence[str]] = None) -> Tuple[int, dict]:
        """Adds every member of the « Compétition » tariff not already listed (not invited), only those at one of
        `statuses` when given. Returns (number added, competition)."""
        added, doc = CompetitionRepository.load_competition_group_doc(competition_id, statuses)
        return added, _written(competition_id, doc)
