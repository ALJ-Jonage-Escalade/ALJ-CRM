"""Coaches CRUD; the competitions store coach ids only (names are resolved when read)."""
from typing import Dict, Any, Optional

from domain.competitions.models import coach_ids_of
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions.base import CompetitionStoreBase


class CoachesMixin(CompetitionStoreBase):
    """`coaches` collection; deleting a coach removes it from their competitions."""

    # ------------------------------------------------------------------
    # CRUD Coachs
    # ------------------------------------------------------------------
    @classmethod
    def list_coaches(cls) -> list:
        docs = FirestoreClient.list_documents(cls.COLLECTION_COACHES)
        result = [cls._coach_dict(d) for d in docs if d.get("id") is not None]
        result.sort(key=lambda c: (c["nom"] or "").lower())
        return result

    @staticmethod
    def _coach_dict(doc: Dict[str, Any]) -> dict:
        return {"id": doc.get("id"), "nom": str(doc.get("nom") or "")}

    @classmethod
    def get_coach(cls, coach_id: int) -> Optional[dict]:
        doc = FirestoreClient.get_document(cls.COLLECTION_COACHES, str(coach_id))
        return cls._coach_dict(doc) if doc else None

    @classmethod
    def save_coach(cls, nom: str, coach_id: int = None) -> int:
        ret_id = coach_id or cls._new_id()
        FirestoreClient.upsert_document(cls.COLLECTION_COACHES, str(ret_id),
                                        {"id": ret_id, "nom": nom, "updated_at": cls._now_iso()})
        return ret_id

    @classmethod
    def delete_coach(cls, coach_id: int) -> bool:
        existed = FirestoreClient.delete_document(cls.COLLECTION_COACHES, str(coach_id))
        cls._patch_competitions_of_coach(
            coach_id, lambda ids: {"coach_ids": [cid for cid in ids if cid != coach_id]}, "Retrait du coach")
        return existed

    @classmethod
    def _patch_competitions_of_coach(cls, coach_id: int, make_patch, what: str):
        """Applies `make_patch(coach_ids)` to every competition of the coach. One write per
        competition, no rollback: a failure is logged and the others still go through (A10)."""
        for doc in cls._list_comp_docs():
            ids = coach_ids_of(doc)
            if coach_id not in ids:
                continue
            try:
                FirestoreClient.update_fields(cls.COLLECTION_COMPETITIONS, str(doc.get("id")),
                                              {**make_patch(ids), "updated_at": cls._now_iso()})
            except FirestoreError as e:
                print(f"⚠️ [FIRESTORE] {what} #{coach_id} sur l'épreuve "
                      f"#{doc.get('id')} impossible : {e}")
