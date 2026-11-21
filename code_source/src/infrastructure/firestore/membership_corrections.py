"""The admin's corrections of HelloAsso registrations, in Firestore: collection `helloasso_membership_corrections`, one
document per registration and season (id `<season>-<item id>`), with per field the corrected value, the HelloAsso
value seen, the author and the date.

Read and written by the server only (firestore.rules refuses every client). No `crm_` prefix: not copied into the
SQLite cache. Kept after the import (tiny, keeps the trace). Read whole and filtered on the season: a few hundred
documents a season.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from domain.members.import_corrections import Corrections, FieldCorrection
from domain.members.member_data_rules import IssueField, is_issue_field
from infrastructure.firestore.client import FirestoreClient

logger = logging.getLogger("alj")

COLLECTION = "helloasso_membership_corrections"


def _doc_id(season: str, item_id: int) -> str:
    return f"{season}-{item_id}"


def _correction(field: IssueField, raw: Dict[str, Any]) -> FieldCorrection:  # Any: a Firestore map
    return FieldCorrection(field=field, value=str(raw.get("value") or ""), helloasso_value=str(raw.get("helloasso_value") or ""),
                           author=str(raw.get("author") or ""), at=str(raw.get("at") or ""))


def _stored(correction: FieldCorrection) -> Dict[str, str]:
    return {"value": correction.value, "helloasso_value": correction.helloasso_value, "author": correction.author, "at": correction.at}


class MembershipCorrections:

    @staticmethod
    def for_season(season: str) -> Corrections:
        """The corrections of the season's registrations, by HelloAsso item id then field."""
        corrections: Dict[int, Dict[IssueField, FieldCorrection]] = {}
        for doc in FirestoreClient.list_documents(COLLECTION):
            if doc.get("season") != season or not isinstance(doc.get("item_id"), int):
                continue
            fields: Dict[IssueField, FieldCorrection] = {}
            for field, raw in (doc.get("fields") or {}).items():
                if is_issue_field(field) and isinstance(raw, dict):
                    fields[field] = _correction(field, raw)
                else:
                    logger.warning("Correction HelloAsso %s : champ inconnu %s ignoré", doc.get("_doc_id"), field)
            if fields:
                corrections[doc["item_id"]] = fields
        return corrections

    @staticmethod
    def save(season: str, item_id: int, correction: FieldCorrection) -> None:
        """Writes the correction of one field, replacing the former one of that field."""
        doc = FirestoreClient.get_document(COLLECTION, _doc_id(season, item_id)) or {}
        fields = dict(doc.get("fields") or {})
        fields[correction.field] = _stored(correction)
        FirestoreClient.upsert_document(COLLECTION, _doc_id(season, item_id), {"season": season, "item_id": item_id, "fields": fields})

    @staticmethod
    def remove(season: str, item_id: int, field: IssueField) -> None:
        """Removes the correction of one field (nothing when there is none); the document goes with its last field."""
        doc = FirestoreClient.get_document(COLLECTION, _doc_id(season, item_id))
        if doc is None:
            return
        fields = {name: value for name, value in (doc.get("fields") or {}).items() if name != field}
        if fields:
            FirestoreClient.upsert_document(COLLECTION, _doc_id(season, item_id), {"season": season, "item_id": item_id, "fields": fields})
        else:
            FirestoreClient.delete_document(COLLECTION, _doc_id(season, item_id))
