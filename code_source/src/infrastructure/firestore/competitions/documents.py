"""Competition documents on Firestore: collection names, time and retry helpers, and the
competition documents themselves (read, identifier normalization, building, participant writes).

Firestore model of the competitions domain (one module per domain in this package):

- `competitions/{id}`         : competition + embedded `participants` array;
- `coaches/{id}`              : coaches;
- `adherents/{id}`            : snapshot of the members (mirror of database.db);
- `helloasso_items/{id_item}` : mirror of the HelloAsso payments + their links.

Identifier normalization: legacy documents created by the web page had a random Firestore
id. When the competitions are listed, such a document is copied to the canonical id `str(id)`
and the legacy one deleted; writes always target the canonical id.
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Callable, Optional, TypedDict, TypeVar, cast

from domain.competitions.models import LEGACY_COACH_SLOTS, Competition, PaymentStatus, coach_ids_of, default_deadline
from infrastructure.firestore.client import (
    META_KEYS,
    FirestoreClient,
    FirestoreConflictError,
    FirestoreError,
)

logger = logging.getLogger("alj")

COLLECTION_COMPETITIONS = "competitions"
COLLECTION_COACHES = "coaches"
COLLECTION_ADHERENTS = "adherents"
COLLECTION_PLANNING = "planning"
COLLECTION_ITEMS = "helloasso_items"

# Optimistic lock on the participants: number of attempts (re-read + change replayed) when
# another device, the web page or the HelloAsso webhook changed the competition between the
# read and the write.
_MAX_WRITE_ATTEMPTS = 5

_Result = TypeVar("_Result")


class ParticipantDoc(TypedDict, total=False):
    """A participant row of a competition document as the pages get it (api.competitions.schemas.views.
    CompetitionParticipant). Rows written by older versions may miss fields, hence total=False."""
    participant_id: Optional[int]  # the member id again (written by every new row)
    adherent_id: Optional[int]
    nom: str
    prenom: str
    num_licence: str
    tarif: str
    phone: str
    email: str
    urgence_nom: str
    urgence_tel: str
    selectionne: bool
    present: bool
    statut_paiement: str
    montant_paye: float
    commande_helloasso: str
    date_synchro_helloasso: str
    note_paiement: str
    classement: str
    total_categorie: int | str
    categorie_ffme: str
    performance_ffme: str
    resultat_ffme: str
    resultat_synced_at: str
    sex: Optional[str]
    updated_at: str


class CompetitionDoc(TypedDict, total=False):
    """A competition document as the pages get it (api_doc: api.competitions.schemas.views.Competition), with its
    stored counters and timestamps. Documents written by older versions may miss fields, hence total=False."""
    id: int
    id_ffme: str
    nom: str
    date_competition: str
    date_fin: str
    deadline: str
    prix: float
    statut: str
    lieu: Optional[str]  # pass-through fields of the office page, stored as given
    type: Optional[str]
    whatsapp_link: str
    url_resultats: str
    id_resultat_ffme: str  # results page number entered before url_resultats existed
    resultats_synced_at: str
    resultats_url_demandee_at: str  # set once the results batch asked for the URL by e-mail
    coach_ids: list[int]
    coaches: list[str]  # names of coach_ids, resolved from the coaches collection
    participants: list[ParticipantDoc]
    nb_participants: int
    nb_selectionnes: int
    nb_payes: int
    total_collecte: float
    created_at: str
    updated_at: str


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def row_stamp() -> str:
    """`updated_at` of a participant row: to the microsecond, since a change queued offline is refused only when
    the row's stamp differs from the one the phone saw (unchanged_since_guard). To the second, a change made
    elsewhere in that same second went unnoticed. Still ISO: compares as a string with the older stamps."""
    return datetime.datetime.now().isoformat(timespec="microseconds")


def now_display() -> str:
    """Timestamp format of the HelloAsso mirror and payment dates."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def comp_sort_key(date_competition: Any, competition_id: Any) -> tuple[str, int]:
    """Competitions are ordered by date, then id (creation order). Any: raw document values."""
    return str(date_competition or ""), int(competition_id or 0)


def with_retries(what: str, attempt: Callable[[], _Result]) -> _Result:
    """Runs `attempt()` again (re-reading inside it) when its conditional write lost a
    race (FirestoreConflictError), up to _MAX_WRITE_ATTEMPTS times; the last conflict propagates."""
    for attempt_number in range(_MAX_WRITE_ATTEMPTS - 1):
        try:
            return attempt()
        except FirestoreConflictError:
            logger.info(f"[FIRESTORE] {what} modifié(e) entre-temps : "
                        f"nouvelle tentative ({attempt_number + 2}/{_MAX_WRITE_ATTEMPTS})")
            time.sleep(0.2 * (attempt_number + 1))
    return attempt()


def new_id() -> int:
    """Business identifier of a new document (same convention as the PWA)."""
    return int(time.time() * 1000)


def list_comp_docs() -> list[dict[str, Any]]:
    """Every `competitions` document, deduplicated by business identifier.

    One business identifier can exist under two documents (legacy PWA creation with a random
    Firestore id): the most recent document wins, it is copied to the canonical id `str(id)`
    and the duplicates are deleted."""
    docs = FirestoreClient.list_documents(COLLECTION_COMPETITIONS)
    kept: dict[str, dict[str, Any]] = {}
    for doc in docs:
        if doc.get("id") is None:
            kept.setdefault(str(doc.get("_doc_id") or ""), doc)
            continue
        key = str(doc.get("id"))
        current = kept.get(key)
        if current is None or str(doc.get("updated_at") or "") > str(current.get("updated_at") or ""):
            kept[key] = doc
    for key, doc in list(kept.items()):
        if doc.get("id") is None:
            continue
        doc_id = doc.get("_doc_id") or key
        if doc_id == key:
            continue
        try:
            FirestoreClient.upsert_document(COLLECTION_COMPETITIONS, key, clean_doc(doc))
            FirestoreClient.delete_document(COLLECTION_COMPETITIONS, doc_id)
            doc["_doc_id"] = key
        except FirestoreError as e:
            logger.warning(f"[FIRESTORE] Normalisation de l'épreuve #{key} impossible : {e}")
    return list(kept.values())


def load_comp_doc(competition_id: int | str) -> dict[str, Any] | None:
    """The document of a competition (fast path: canonical identifier)."""
    wanted = str(competition_id)
    doc = FirestoreClient.get_document(COLLECTION_COMPETITIONS, wanted)
    if doc is not None and str(doc.get("id")) == wanted:
        return doc
    matches = [d for d in list_comp_docs() if str(d.get("id")) == wanted]
    return matches[0] if matches else None


def _coach_names(coach_ids: list[int], coaches: dict[int, str]) -> list[str]:
    return [coaches[coach_id] for coach_id in coach_ids if coach_id in coaches]


def api_doc(doc: dict[str, Any], coaches: dict[int, str]) -> CompetitionDoc:
    """Document for the web pages: `coach_ids` normalized (legacy slots read too) and
    `coaches` resolved from the coaches collection, never the stored copy. Only a deadline set by
    hand is stored: the default one (1 week before the start) follows the start date."""
    # The stored fields as they are (no conversion): a Firestore document, shaped as CompetitionDoc by the writers
    out = cast(CompetitionDoc, {k: v for k, v in clean_doc(doc).items() if k not in LEGACY_COACH_SLOTS})
    out["deadline"] = str(doc.get("deadline") or "").strip() or default_deadline(str(doc.get("date_competition") or ""))
    out["coach_ids"] = coach_ids_of(doc)
    out["coaches"] = _coach_names(out["coach_ids"], coaches)
    return out


def comp_from_doc(doc: dict[str, Any]) -> Competition:
    row = {
        "id": doc.get("id"),
        "id_ffme": doc.get("id_ffme"),
        "nom": doc.get("nom"),
        "date_competition": doc.get("date_competition"),
        "date_fin": doc.get("date_fin"),
        "deadline": doc.get("deadline"),
        "prix": doc.get("prix"),
        "statut": doc.get("statut"),
        "url_resultats": doc.get("url_resultats"),
        "resultats_synced_at": doc.get("resultats_synced_at"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "whatsapp_link": doc.get("whatsapp_link"),
        "_doc_id": doc.get("_doc_id"),
        "coach_ids": doc.get("coach_ids"),
        **{slot: doc.get(slot) for slot in LEGACY_COACH_SLOTS},
    }
    return Competition.from_row(row)


def build_comp_doc(doc: dict[str, Any] | None, comp: Competition) -> dict[str, Any]:
    """Complete document ready to be written (participants kept)."""
    parts = (doc or {}).get("participants") or []
    now = now_iso()
    new_doc = {
        "id": comp.id,
        "id_ffme": comp.id_ffme or "",
        "nom": comp.nom or "",
        "date_competition": comp.date_competition or "",
        "date_fin": comp.date_fin or "",
        "deadline": (comp.deadline or "").strip(),
        "prix": float(comp.prix or 0.0),
        "statut": comp.statut,
        "url_resultats": comp.url_resultats or "",
        "resultats_synced_at": comp.resultats_synced_at or "",
        "whatsapp_link": comp.whatsapp_link or "",
        "coach_ids": list(comp.coach_ids),
        "participants": parts,
        "created_at": (doc or {}).get("created_at") or now,
        "updated_at": now,
    }
    new_doc.update(recompute_counters(parts))
    return new_doc


def recompute_counters(parts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "nb_participants": len(parts),
        "nb_selectionnes": sum(1 for p in parts if p.get("selectionne")),
        "nb_payes": sum(1 for p in parts if (p.get("statut_paiement") or "") == PaymentStatus.PAYE),
        "total_collecte": round(sum(float(p.get("montant_paye") or 0.0) for p in parts), 2),
    }


def save_parts(doc: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Rewrites the participants array + counters (partial update); returns the fields written.

    The write is conditioned on the version read (`_update_time`): if the document changed
    since, FirestoreConflictError is raised and nothing is written (see
    participants.mutate_participants, which replays the change)."""
    patch = {"participants": parts, "updated_at": now_iso()}
    patch.update(recompute_counters(parts))
    FirestoreClient.update_fields(
        COLLECTION_COMPETITIONS, doc.get("_doc_id") or str(doc.get("id")), patch,
        expected_update_time=doc.get("_update_time"),
    )
    return patch


def clean_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """The document without the metadata keys the client adds (`_doc_id`, `_update_time`)."""
    return {k: v for k, v in doc.items() if k not in META_KEYS}


def coaches_map() -> dict[int, str]:
    """{coach id -> name}; empty when the coaches cannot be read (the names then show as missing)."""
    try:
        docs = FirestoreClient.list_documents(COLLECTION_COACHES)
    except Exception:
        logger.warning("[FIRESTORE] Lecture des coachs impossible : noms non résolus", exc_info=True)
        return {}
    return {d["id"]: str(d.get("nom") or "") for d in docs if d.get("id") is not None}
