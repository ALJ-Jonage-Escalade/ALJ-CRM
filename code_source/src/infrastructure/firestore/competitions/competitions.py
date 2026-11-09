"""Competition documents: read (as the `Competition` model, as stored, or shaped for the web pages),
create, update under the optimistic lock, archive and delete."""
from __future__ import annotations

import logging
from typing import Any, Callable

from domain.competitions.models import STATUT_CLOSE, Competition
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import documents, member_directory

logger = logging.getLogger("alj")

# Fields of the participants array: never rewritten by a change to the competition itself
_PARTICIPANT_FIELDS = {"participants", "nb_participants", "nb_selectionnes", "nb_payes", "total_collecte"}


def list_competitions() -> list[Competition]:
    """Every competition, most recent first."""
    competitions = [documents.comp_from_doc(doc) for doc in documents.list_comp_docs()]
    competitions.sort(key=lambda comp: documents.comp_sort_key(comp.date_competition, comp.id), reverse=True)
    return competitions


def get_competition(competition_id: int) -> Competition | None:
    doc = documents.load_comp_doc(competition_id)
    return documents.comp_from_doc(doc) if doc else None


def list_competition_docs() -> list[dict[str, Any]]:
    """Competition documents as stored (participants and counters included), most
    recent first: the shape the web pages use."""
    coaches = documents.coaches_map()
    sexes = _member_sexes()
    docs = [_with_member_sex(documents.api_doc(doc, coaches), sexes) for doc in documents.list_comp_docs()]
    docs.sort(key=lambda doc: documents.comp_sort_key(doc.get("date_competition"), doc.get("id")), reverse=True)
    return docs


def get_stored_competition_doc(competition_id: int) -> dict[str, Any] | None:
    """The competition's document as stored (no API shaping), None when unknown: for workflows reading its fields."""
    return documents.load_comp_doc(competition_id)


def get_competition_doc(competition_id: int) -> dict[str, Any] | None:
    """The competition's document shaped for the web pages (see competition_api_doc), None when unknown."""
    doc = documents.load_comp_doc(competition_id)
    return competition_api_doc(doc) if doc else None


def competition_api_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Shape of get_competition_doc for a document already read or just written (the
    participant writes return it): saves reading it again."""
    return _with_member_sex(documents.api_doc(doc, documents.coaches_map()), _member_sexes())


def _member_sexes() -> dict[int, str | None]:
    """{adherent id -> sex code} from the `adherents` directory: the single source of the participants'
    sex (plans/sex-enum.md D7). Empty when the directory cannot be read: the sexes show as not given."""
    try:
        return {doc["id"]: member_directory.sex_code(doc) for doc in member_directory.adherents_raw() if doc.get("id") is not None}
    except FirestoreError as e:
        logger.warning("Annuaire adhérents illisible, sexe des participants non renseigné : %s", e)
        return {}


def _with_member_sex(doc: dict[str, Any], sexes: dict[int, str | None]) -> dict[str, Any]:
    """The API document with each participant's `sex` read from its member (the copy older rows hold,
    `gender`, is dropped). Participant maps are copied: `doc` may share them with a cached document."""
    participants = []
    for participant in doc.get("participants") or []:
        row = {k: v for k, v in participant.items() if k != "gender"}
        row["sex"] = sexes.get(participant.get("adherent_id"))
        participants.append(row)
    return {**doc, "participants": participants}


def archive_past_competitions(today_iso: str) -> list[int]:
    """Closes every competition that ended before `today_iso` (YYYY-MM-DD); competitions
    without a date are never past. Returns the ids archived."""
    archived = []
    for doc in documents.list_comp_docs():
        end = str(doc.get("date_fin") or doc.get("date_competition") or "")
        if doc.get("id") is None or not end or end >= today_iso:
            continue
        if (doc.get("statut") or "") == STATUT_CLOSE:
            continue
        FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, str(doc["id"]),
                                      {"statut": STATUT_CLOSE, "updated_at": documents.now_iso()})
        archived.append(doc["id"])
    return archived


def save_competition(comp: Competition, extra: dict[str, Any] | None = None) -> int:
    """Inserts or updates a competition; returns its id.

    `extra`: fields outside the domain model, stored as given (pass-through fields
    of the bureau page, see documentations/plan_api_only_front.md appendix B)."""
    existing = documents.load_comp_doc(comp.id) if comp.id else None
    if comp.id is None:
        comp.id = documents.new_id()
    doc = documents.build_comp_doc(existing, comp)
    doc.update(extra or {})
    if existing and (existing.get("_doc_id") or str(comp.id)) == str(comp.id):
        FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, str(comp.id), _info_fields(doc))
    else:
        FirestoreClient.upsert_document(documents.COLLECTION_COMPETITIONS, str(comp.id), doc)
    return comp.id


def _info_fields(doc: dict[str, Any]) -> dict[str, Any]:
    """Competition information only: the participants array and its counters are not
    rewritten, so as not to overwrite a concurrent change to them."""
    return {k: v for k, v in doc.items() if k not in _PARTICIPANT_FIELDS}


def update_competition(competition_id: int, change: Callable[[Competition], object],
                       extra: dict[str, Any] | None = None) -> bool:
    """Partial update of an existing competition: `change(comp)` edits the Competition read
    from the document, written back on the version read (optimistic lock). On conflict
    (results batch, webhook, another coach) the document is read again and `change`
    replayed, so a field it does not set keeps the value written meanwhile.
    Returns False when the competition does not exist."""
    def attempt() -> bool:
        existing = documents.load_comp_doc(competition_id)
        if not existing:
            return False
        comp = documents.comp_from_doc(existing)
        change(comp)
        doc = documents.build_comp_doc(existing, comp)
        doc.update(extra or {})
        FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, existing.get("_doc_id") or str(comp.id),
                                      _info_fields(doc), expected_update_time=existing.get("_update_time"))
        return True
    return bool(documents.with_retries(f"Épreuve #{competition_id}", attempt))


def delete_competition(competition_id: int) -> bool:
    """Deletes the competition; False when it does not exist."""
    doc = documents.load_comp_doc(competition_id)
    if not doc:
        return False
    FirestoreClient.delete_document(documents.COLLECTION_COMPETITIONS, str(doc.get("id")))
    return True
