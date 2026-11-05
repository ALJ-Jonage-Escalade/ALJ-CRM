"""Shared base of the competition repository mixins: collection names, time and retry
helpers, and the competition documents (read, normalization, building, participant writes)."""
import time
import datetime
from typing import Dict, Any, List, Optional

from domain.competitions.models import (
    LEGACY_COACH_SLOTS,
    Competition,
    coach_ids_of,
    default_deadline,
    PAIEMENT_PAYE,
)
from infrastructure.firestore.client import (
    META_KEYS,
    FirestoreClient,
    FirestoreConflictError,
    FirestoreError,
)

# Verrouillage optimiste des participants : nombre de tentatives (relecture +
# ré-application de la modification) quand un autre poste, la page web ou le
# webhook HelloAsso a modifié l'épreuve entre la lecture et l'écriture.
_MAX_WRITE_ATTEMPTS = 5


class CompetitionStoreBase:
    """Internal tools shared by every mixin (all classmethods)."""

    COLLECTION_COMPETITIONS = "competitions"
    COLLECTION_COACHES = "coaches"
    COLLECTION_ADHERENTS = "adherents"
    COLLECTION_PLANNING = "planning"
    COLLECTION_ITEMS = "helloasso_items"

    # ------------------------------------------------------------------
    # Outils internes : documents de compétition
    # ------------------------------------------------------------------
    @classmethod
    def _now_iso(cls) -> str:
        return datetime.datetime.now().isoformat(timespec="seconds")

    @classmethod
    def _row_stamp(cls) -> str:
        """`updated_at` of a participant row: to the microsecond, since a change queued offline is refused only when
        the row's stamp differs from the one the phone saw (unchanged_since_guard). To the second, a change made
        elsewhere in that same second went unnoticed. Still ISO: compares as a string with the older stamps."""
        return datetime.datetime.now().isoformat(timespec="microseconds")

    @classmethod
    def _now_display(cls) -> str:
        """Timestamp format of the HelloAsso mirror and payment dates."""
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _comp_sort_key(date_competition, competition_id) -> tuple:
        """Competitions are ordered by date, then id (creation order)."""
        return str(date_competition or ""), int(competition_id or 0)

    @staticmethod
    def _with_retries(what: str, attempt):
        """Runs `attempt()` again (re-reading inside it) when its conditional write lost a
        race (FirestoreConflictError), up to _MAX_WRITE_ATTEMPTS times."""
        for n in range(_MAX_WRITE_ATTEMPTS):
            try:
                return attempt()
            except FirestoreConflictError:
                if n == _MAX_WRITE_ATTEMPTS - 1:
                    raise
                print(f"🔁 [FIRESTORE] {what} modifié(e) entre-temps : "
                      f"nouvelle tentative ({n + 2}/{_MAX_WRITE_ATTEMPTS})")
                time.sleep(0.2 * (n + 1))
        return None

    @classmethod
    def _new_id(cls) -> int:
        """Identifiant métier d'un nouveau document (même convention que la PWA)."""
        return int(time.time() * 1000)

    @classmethod
    def _list_comp_docs(cls) -> List[Dict[str, Any]]:
        """Tous les documents `competitions`, dédoublonnés par identifiant métier.

        Un même identifiant métier peut exister sous deux documents (création PWA
        historique avec identifiant Firestore aléatoire) : le document le plus
        récent gagne, il est recopié vers l'identifiant canonique `str(id)` et
        les doublons sont supprimés."""
        docs = FirestoreClient.list_documents(cls.COLLECTION_COMPETITIONS)
        kept: Dict[str, Dict[str, Any]] = {}
        for d in docs:
            if d.get("id") is None:
                key = d.get("_doc_id")
                kept.setdefault(key, d)
                continue
            key = str(d.get("id"))
            current = kept.get(key)
            if current is None or str(d.get("updated_at") or "") > str(current.get("updated_at") or ""):
                kept[key] = d
        for key, doc in list(kept.items()):
            if doc.get("id") is None:
                continue
            doc_id = doc.get("_doc_id") or key
            if doc_id == key:
                continue
            try:
                FirestoreClient.upsert_document(cls.COLLECTION_COMPETITIONS, key, cls._clean_doc(doc))
                FirestoreClient.delete_document(cls.COLLECTION_COMPETITIONS, doc_id)
                doc["_doc_id"] = key
            except FirestoreError as e:
                print(f"⚠️ [FIRESTORE] Normalisation de l'épreuve #{key} impossible : {e}")
        return list(kept.values())

    @classmethod
    def _load_comp_doc(cls, competition_id) -> Optional[Dict[str, Any]]:
        """Charge le document d'une épreuve (chemin rapide : identifiant canonique)."""
        wanted = str(competition_id)
        doc = FirestoreClient.get_document(cls.COLLECTION_COMPETITIONS, wanted)
        if doc is not None and str(doc.get("id")) == wanted:
            return doc
        matches = [d for d in cls._list_comp_docs() if str(d.get("id")) == wanted]
        return matches[0] if matches else None

    @staticmethod
    def _coach_names(coach_ids, coaches: Dict[int, str]) -> List[str]:
        return [coaches[cid] for cid in coach_ids if cid is not None and cid in coaches]

    @classmethod
    def _legacy_coach_fields(cls, coach_ids: List[int], coaches: Dict[int, str]) -> Dict[str, Any]:
        """Copies of `coach_ids` kept for desktop builds older than plan C2, which read
        `coach1_id..coach3_id` (first three coaches) and the stored `coaches` names.
        Remove with plan C2 step B, once every club PC runs the new version."""
        ids = list(coach_ids)[:len(LEGACY_COACH_SLOTS)]
        ids += [None] * (len(LEGACY_COACH_SLOTS) - len(ids))
        return {**dict(zip(LEGACY_COACH_SLOTS, ids, strict=True)), "coaches": cls._coach_names(coach_ids, coaches)}

    @classmethod
    def _api_doc(cls, doc: Dict[str, Any], coaches: Dict[int, str]) -> Dict[str, Any]:
        """Document for the web pages: `coach_ids` normalized (legacy slots read too) and
        `coaches` resolved from the coaches collection, never the stored copy. Only a deadline set by
        hand is stored: the default one (1 week before the start) follows the start date."""
        out = cls._clean_doc(doc)
        out["deadline"] = str(doc.get("deadline") or "").strip() or default_deadline(str(doc.get("date_competition") or ""))
        out["coach_ids"] = coach_ids_of(doc)
        out["coaches"] = cls._coach_names(out["coach_ids"], coaches)
        return out

    @classmethod
    def _comp_from_doc(cls, doc: Dict[str, Any]) -> Competition:
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

    @classmethod
    def _build_comp_doc(cls, doc: Optional[Dict[str, Any]], comp: Competition,
                        coaches: Dict[int, str]) -> Dict[str, Any]:
        """Document complet prêt à être écrit (participants préservés)."""
        parts = (doc or {}).get("participants") or []
        now = cls._now_iso()
        new_doc = {
            "id": comp.id,
            "id_ffme": comp.id_ffme or "",
            "nom": comp.nom or "",
            "date_competition": comp.date_competition or "",
            "date_fin": comp.date_fin or "",
            "deadline": (comp.deadline or "").strip(),
            "prix": float(comp.prix or 0.0),
            "statut": comp.statut or "en_preparation",
            "url_resultats": comp.url_resultats or "",
            "resultats_synced_at": comp.resultats_synced_at or "",
            "whatsapp_link": comp.whatsapp_link or "",
            "coach_ids": list(comp.coach_ids),
            **cls._legacy_coach_fields(comp.coach_ids, coaches),
            "participants": parts,
            "created_at": (doc or {}).get("created_at") or now,
            "updated_at": now,
        }
        new_doc.update(cls._recompute_counters(parts))
        return new_doc

    @classmethod
    def _recompute_counters(cls, parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "nb_participants": len(parts),
            "nb_selectionnes": sum(1 for p in parts if p.get("selectionne")),
            "nb_payes": sum(1 for p in parts if (p.get("statut_paiement") or "") == PAIEMENT_PAYE),
            "total_collecte": round(sum(float(p.get("montant_paye") or 0.0) for p in parts), 2),
        }

    @classmethod
    def _save_parts(cls, doc: Dict[str, Any], parts: List[Dict[str, Any]]):
        """Réécrit le tableau des participants + compteurs (mise à jour partielle).

        L'écriture est conditionnée à la version lue (`_update_time`) : si le
        document a changé depuis, `FirestoreConflictError` est levée et rien
        n'est écrit (voir `_mutate_participants`, qui rejoue la modification)."""
        patch = {"participants": parts, "updated_at": cls._now_iso()}
        patch.update(cls._recompute_counters(parts))
        FirestoreClient.update_fields(
            cls.COLLECTION_COMPETITIONS, doc.get("_doc_id") or str(doc.get("id")), patch,
            expected_update_time=doc.get("_update_time"),
        )
        return patch

    @classmethod
    def _clean_doc(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in doc.items() if k not in META_KEYS}

    @classmethod
    def _coaches_map(cls) -> Dict[int, str]:
        try:
            docs = FirestoreClient.list_documents(cls.COLLECTION_COACHES)
        except Exception:
            return {}
        return {d.get("id"): str(d.get("nom") or "") for d in docs if d.get("id") is not None}

    # ------------------------------------------------------------------
    # Compatibilité avec l'ancien référentiel SQLite
    # ------------------------------------------------------------------
    @classmethod
    def setup_database(cls, force: bool = False):
        """Aucune action : les collections Firestore existent par nature."""
        return None

    @classmethod
    def get_db_path(cls) -> str:
        """Ancienne API (SQLite) : conservée pour compatibilité, inutilisée."""
        return ""
