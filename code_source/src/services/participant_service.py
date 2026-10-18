"""Participants of a competition (array embedded in the competition document).

Every write goes through the repository's optimistic lock (re-read and retried on a
concurrent change). Knows nothing about HTTP: failures are raised as services.errors.
"""

from typing import Optional, Tuple

from infrastructure.competition_firestore_repository import (
    CompetitionFirestoreRepository as Repo,
    ParticipantAlreadyPaid,
)
from services.competition_store import require_competition, write
from services.errors import Conflict, NotFound


def _written(competition_id: int, doc: Optional[dict]) -> dict:
    """The competition as the write left it. `doc` None (nothing written): the competition is
    read, which also raises NotFound when it does not exist."""
    return Repo.competition_api_doc(doc) if doc is not None else require_competition(competition_id)


def _participant_not_found(competition_id: int) -> NotFound:
    require_competition(competition_id)  # unknown competition: its own message
    return NotFound("Compétiteur absent de cette compétition.")


class ParticipantService:
    """Each write answers with the document it wrote: one read of the competition (inside
    the write) instead of an existence check before and a read after."""

    @staticmethod
    @write
    def add_participant(competition_id: int, adherent_id: int, selectionne: bool) -> dict:
        return _written(competition_id, Repo.add_participant_doc(competition_id, adherent_id, selectionne))

    @staticmethod
    @write
    def update_participant(competition_id: int, adherent_id: int,
                           selectionne: Optional[bool] = None,
                           present: Optional[bool] = None) -> dict:
        """Unselecting a participant who paid is refused (Conflict `already_paid`): the
        coach must then choose whether the money is lost or carried over (cancel_participant)."""
        doc = None
        if selectionne is not None:
            try:
                doc = Repo.set_selection_doc(competition_id, adherent_id, selectionne, refuse_unselect_paid=True)
            except ParticipantAlreadyPaid as e:
                raise Conflict("Ce compétiteur a déjà payé : choisissez le sort de son paiement.",
                               "already_paid") from e
        if present is not None:
            doc = Repo.set_present_doc(competition_id, adherent_id, present)
            if doc is None:
                raise _participant_not_found(competition_id)
        return _written(competition_id, doc)

    @staticmethod
    @write
    def record_manual_payment(competition_id: int, adherent_id: int, montant: float) -> dict:
        """Cheque or cash: the participant becomes selected and paid."""
        doc = Repo.record_manual_payment_doc(competition_id, adherent_id, montant)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return Repo.competition_api_doc(doc)

    @staticmethod
    @write
    def cancel_participant(competition_id: int, adherent_id: int, payment_status: str,
                           note: str) -> dict:
        """`payment_status`: PAIEMENT_ANNULE_PERDU or PAIEMENT_ANNULE_REPORTE."""
        doc = Repo.mark_cancelled_doc(competition_id, adherent_id, payment_status, note)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return Repo.competition_api_doc(doc)

    @staticmethod
    @write
    def remove_participant(competition_id: int, adherent_id: int) -> dict:
        doc = Repo.remove_participant_doc(competition_id, adherent_id)
        if doc is None:
            raise NotFound("Compétition ou compétiteur introuvable.")
        return Repo.competition_api_doc(doc)

    @staticmethod
    @write
    def load_competition_group(competition_id: int) -> Tuple[int, dict]:
        """Adds every member of the « Compétition » tariff not already listed (not invited).
        Returns (number added, competition)."""
        added, doc = Repo.load_competition_group_doc(competition_id)
        return added, _written(competition_id, doc)
