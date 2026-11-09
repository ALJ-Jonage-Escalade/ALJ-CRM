"""HelloAsso mirror items: manual links to a participant, and ignored items.

Knows nothing about HTTP: failures are raised as domain.errors.
"""

from __future__ import annotations

from typing import List, Optional

from infrastructure.firestore.competition_repository import (
    CompetitionFirestoreRepository as Repo,
    ItemAlreadyLinked,
)
from services.competitions.store import competition_not_found, storage, write
from services.documents import Doc
from domain.errors import Conflict, InvalidRequest, NotFound


def _item_not_found() -> NotFound:
    return NotFound("Article HelloAsso introuvable.")


class HelloAssoItemService:

    @staticmethod
    @storage
    def list_items() -> List[Doc]:
        return Repo.list_item_docs()

    @staticmethod
    @write
    def link_item(id_item: int, competition_id: Optional[int], adherent_id: Optional[int],
                  commentaire: str) -> bool:
        """Saves the coach's link. When both a competition and a member are chosen, the member
        is (re)selected for the competition and their payment recomputed from all the paid
        items linked to them (a refunded or pending item adds nothing). The participant the
        item was linked to before has theirs recomputed too: the item no longer pays for them.
        Returns whether the item is now linked to a participant."""
        item = Repo.get_item(id_item)
        if item is None:
            raise _item_not_found()
        if competition_id is not None and Repo.get_competition(competition_id) is None:
            raise competition_not_found()
        prev_comp, prev_adherent = item.get("competition_id"), item.get("adherent_id")
        Repo.save_manual_link(id_item, competition_id, adherent_id, commentaire)
        linked = False
        if competition_id is not None and adherent_id is not None:
            linked = True
            Repo.add_participant(competition_id, adherent_id, selectionne=True)
            Repo.refresh_helloasso_payment(competition_id, adherent_id)
        if (prev_comp is not None and prev_adherent is not None
                and (prev_comp, prev_adherent) != (competition_id, adherent_id)):
            Repo.refresh_helloasso_payment(prev_comp, prev_adherent)
        return linked

    @staticmethod
    @write
    def ignore_item(id_item: int, ignore: bool, motif: str, commentaire: str, by: str) -> None:
        """Ignores (reason required) or restores an item. Refused (Conflict `already_linked`)
        when the item got linked meanwhile. `by`: e-mail of the coach, kept for audit."""
        if ignore and not motif:
            raise InvalidRequest("Indiquez un motif pour ignorer cette ligne.", "motif_required")
        try:
            found = Repo.set_item_ignored(id_item, ignore, motif, commentaire, by=by)
        except ItemAlreadyLinked as e:
            raise Conflict("Cette ligne vient d'être rattachée à un compétiteur : "
                           "elle ne peut pas être ignorée.", "already_linked") from e
        if not found:
            raise _item_not_found()
