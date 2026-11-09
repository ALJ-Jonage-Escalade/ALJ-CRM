"""`coaches` collection; the competitions store coach ids only (names are resolved when read),
and deleting a coach removes them from their competitions."""
from __future__ import annotations

import logging
from typing import Any, Callable, TypedDict

from domain.competitions.models import coach_ids_of
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import documents

logger = logging.getLogger("alj")


class Coach(TypedDict):
    id: int
    nom: str


def list_coaches() -> list[Coach]:
    """Every coach, by name."""
    docs = FirestoreClient.list_documents(documents.COLLECTION_COACHES)
    result = [_coach_dict(doc) for doc in docs if doc.get("id") is not None]
    result.sort(key=lambda coach: (coach["nom"] or "").lower())
    return result


def _coach_dict(doc: dict[str, Any]) -> Coach:
    return {"id": doc["id"], "nom": str(doc.get("nom") or "")}


def get_coach(coach_id: int) -> Coach | None:
    doc = FirestoreClient.get_document(documents.COLLECTION_COACHES, str(coach_id))
    return _coach_dict(doc) if doc else None


def save_coach(nom: str, coach_id: int | None = None) -> int:
    """Creates the coach (no `coach_id`) or renames them; returns their id."""
    saved_id = coach_id or documents.new_id()
    FirestoreClient.upsert_document(documents.COLLECTION_COACHES, str(saved_id),
                                    {"id": saved_id, "nom": nom, "updated_at": documents.now_iso()})
    return saved_id


def delete_coach(coach_id: int) -> bool:
    """Deletes the coach and removes them from their competitions; returns whether they existed."""
    existed = FirestoreClient.delete_document(documents.COLLECTION_COACHES, str(coach_id))
    _patch_competitions_of_coach(
        coach_id, lambda ids: {"coach_ids": [cid for cid in ids if cid != coach_id]}, "Retrait du coach")
    return existed


def _patch_competitions_of_coach(coach_id: int, make_patch: Callable[[list[int]], dict[str, Any]], what: str) -> None:
    """Applies `make_patch(coach_ids)` to every competition of the coach. One write per
    competition, no rollback: a failure is logged and the others still go through (A10)."""
    for doc in documents.list_comp_docs():
        ids = coach_ids_of(doc)
        if coach_id not in ids:
            continue
        try:
            FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, str(doc.get("id")),
                                          {**make_patch(ids), "updated_at": documents.now_iso()})
        except FirestoreError as e:
            logger.warning(f"[FIRESTORE] {what} #{coach_id} sur l'épreuve "
                           f"#{doc.get('id')} impossible : {e}")
