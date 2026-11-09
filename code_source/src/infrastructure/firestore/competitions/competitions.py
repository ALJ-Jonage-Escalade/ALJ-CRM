"""Competitions CRUD and the end-of-season report."""
import logging
from typing import Dict, Any, List, Optional

from domain.competitions.models import (
    Competition,
    PAIEMENT_NON_INVITE,
    PAIEMENT_ANNULE_PERDU,
    PAIEMENT_ANNULE_REPORTE,
    STATUT_CLOSE,
)
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import documents, member_directory

logger = logging.getLogger("alj")


class CompetitionsMixin:
    """Competition documents; the season report reads the member directory."""

    # ------------------------------------------------------------------
    # CRUD Compétitions
    # ------------------------------------------------------------------
    @classmethod
    def list_competitions(cls) -> List[Competition]:
        docs = documents.list_comp_docs()
        comps = [documents.comp_from_doc(d) for d in docs]
        comps.sort(key=lambda c: documents.comp_sort_key(c.date_competition, c.id), reverse=True)
        return comps

    @classmethod
    def get_competition(cls, competition_id: int) -> Optional[Competition]:
        doc = documents.load_comp_doc(competition_id)
        return documents.comp_from_doc(doc) if doc else None

    @classmethod
    def list_competition_docs(cls) -> List[Dict[str, Any]]:
        """Competition documents as stored (participants and counters included), most
        recent first: the shape the web pages use."""
        coaches = documents.coaches_map()
        sexes = cls._member_sexes()
        docs = [cls._with_member_sex(documents.api_doc(d, coaches), sexes) for d in documents.list_comp_docs()]
        docs.sort(key=lambda d: documents.comp_sort_key(d.get("date_competition"), d.get("id")), reverse=True)
        return docs

    @classmethod
    def get_stored_competition_doc(cls, competition_id: int) -> Optional[Dict[str, Any]]:
        """The competition's document as stored (no API shaping), None when unknown: for workflows reading its fields."""
        return documents.load_comp_doc(competition_id)

    @classmethod
    def get_competition_doc(cls, competition_id: int) -> Optional[Dict[str, Any]]:
        doc = documents.load_comp_doc(competition_id)
        return cls.competition_api_doc(doc) if doc else None

    @classmethod
    def competition_api_doc(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Shape of get_competition_doc for a document already read or just written (the
        participant writes below return it): saves reading it again."""
        return cls._with_member_sex(documents.api_doc(doc, documents.coaches_map()), cls._member_sexes())

    @classmethod
    def _member_sexes(cls) -> Dict[int, Optional[str]]:
        """{adherent id -> sex code} from the `adherents` directory: the single source of the participants'
        sex (plans/sex-enum.md D7). Empty when the directory cannot be read: the sexes show as not given."""
        try:
            return {doc["id"]: member_directory.sex_code(doc) for doc in member_directory.adherents_raw() if doc.get("id") is not None}
        except FirestoreError as e:
            logger.warning("Annuaire adhérents illisible, sexe des participants non renseigné : %s", e)
            return {}

    @staticmethod
    def _with_member_sex(doc: Dict[str, Any], sexes: Dict[int, Optional[str]]) -> Dict[str, Any]:
        """The API document with each participant's `sex` read from its member (the copy older rows hold,
        `gender`, is dropped). Participant maps are copied: `doc` may share them with a cached document."""
        participants = []
        for p in doc.get("participants") or []:
            row = {k: v for k, v in p.items() if k != "gender"}
            row["sex"] = sexes.get(p.get("adherent_id"))
            participants.append(row)
        return {**doc, "participants": participants}

    @classmethod
    def archive_past_competitions(cls, today_iso: str) -> List[int]:
        """Closes every competition that ended before `today_iso` (YYYY-MM-DD); competitions
        without a date are never past. Returns the ids archived."""
        archived = []
        for doc in documents.list_comp_docs():
            end = str(doc.get("date_fin") or doc.get("date_competition") or "")
            if doc.get("id") is None or not end or end >= today_iso:
                continue
            if (doc.get("statut") or "") == STATUT_CLOSE:
                continue
            if cls.set_competition_status(doc["id"], STATUT_CLOSE):
                archived.append(doc["id"])
        return archived

    @classmethod
    def save_competition(cls, comp: Competition, extra: Optional[Dict[str, Any]] = None) -> int:
        """Insère ou met à jour une épreuve ; retourne son identifiant.

        `extra`: fields outside the domain model, stored as given (pass-through fields
        of the bureau page, see documentations/plan_api_only_front.md appendix B)."""
        existing = documents.load_comp_doc(comp.id) if comp.id else None
        if comp.id is None:
            comp.id = documents.new_id()
        doc = documents.build_comp_doc(existing, comp)
        doc.update(extra or {})
        if existing and (existing.get("_doc_id") or str(comp.id)) == str(comp.id):
            FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, str(comp.id), cls._info_fields(doc))
        else:
            FirestoreClient.upsert_document(documents.COLLECTION_COMPETITIONS, str(comp.id), doc)
        return comp.id

    @staticmethod
    def _info_fields(doc: Dict[str, Any]) -> Dict[str, Any]:
        """Competition information only: the participants array and its counters are not
        rewritten, so as not to overwrite a concurrent change to them."""
        skip = {"participants", "nb_participants", "nb_selectionnes", "nb_payes", "total_collecte"}
        return {k: v for k, v in doc.items() if k not in skip}

    @classmethod
    def update_competition(cls, competition_id: int, change, extra: Optional[Dict[str, Any]] = None) -> bool:
        """Partial update of an existing competition: `change(comp)` edits the Competition read
        from the document, written back on the version read (optimistic lock). On conflict
        (results batch, webhook, another coach) the document is read again and `change`
        replayed, so a field it does not set keeps the value written meanwhile.
        Returns False when the competition does not exist."""
        def attempt():
            existing = documents.load_comp_doc(competition_id)
            if not existing:
                return False
            comp = documents.comp_from_doc(existing)
            change(comp)
            doc = documents.build_comp_doc(existing, comp)
            doc.update(extra or {})
            FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, existing.get("_doc_id") or str(comp.id),
                                          cls._info_fields(doc), expected_update_time=existing.get("_update_time"))
            return True
        return bool(documents.with_retries(f"Épreuve #{competition_id}", attempt))

    @classmethod
    def set_competition_status(cls, competition_id: int, statut: str) -> bool:
        doc = documents.load_comp_doc(competition_id)
        if not doc:
            return False
        FirestoreClient.update_fields(documents.COLLECTION_COMPETITIONS, str(doc.get("id")),
                                      {"statut": statut, "updated_at": documents.now_iso()})
        return True

    @classmethod
    def delete_competition(cls, competition_id: int) -> bool:
        doc = documents.load_comp_doc(competition_id)
        if not doc:
            return False
        FirestoreClient.delete_document(documents.COLLECTION_COMPETITIONS, str(doc.get("id")))
        return True

    @classmethod
    def list_competitions_for_coach(cls, coach_id: int) -> List[Competition]:
        return [c for c in cls.list_competitions() if coach_id in c.coach_ids]

    # ------------------------------------------------------------------
    # Bilan de fin d'année
    # ------------------------------------------------------------------
    @staticmethod
    def season_of_date(date_iso: str) -> str:
        raw = str(date_iso or "").strip()[:10]
        try:
            y, m = int(raw[:4]), int(raw[5:7])
        except (ValueError, IndexError):
            return ""
        start = y if m >= 8 else y - 1
        return f"{start}-{start + 1}"

    @staticmethod
    def _bilan_student(p: Dict[str, Any], adherent: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Identity of a member in the season report: participant row, else directory."""
        a = adherent or {}
        return {k: p.get(k) or a.get(k) or "" for k in ("nom", "prenom", "num_licence", "tarif")}

    @classmethod
    def get_bilan(cls, season: str = "") -> dict:
        docs = documents.list_comp_docs()
        comps = [documents.comp_from_doc(d) for d in docs]
        comps.sort(key=lambda c: documents.comp_sort_key(c.date_competition, c.id))
        adh = member_directory.adherent_map()
        if season:
            comps = [c for c in comps if cls.season_of_date(c.date_competition) == season]

        doc_by_id = {d.get("id"): d for d in docs}
        participants_map = {}
        payments_map = {}
        students: Dict[Any, Any] = {}  # Any: keys and values as the participants carry them
        for c in comps:
            doc = doc_by_id.get(c.id) or {}
            for p in (doc.get("participants") or []):
                statut = p.get("statut_paiement") or PAIEMENT_NON_INVITE
                montant = float(p.get("montant_paye") or 0.0)

                if statut == PAIEMENT_ANNULE_REPORTE:
                    # Argent encaissé mais épreuve annulée : pas de participation due,
                    # le montant reste un CRÉDIT pour l'athlète (compense la prochaine
                    # épreuve de la saison dans la balance des paiements).
                    key = p.get("adherent_id")
                    if key is None:
                        continue
                    students.setdefault(key, cls._bilan_student(p, adh.get(key)))
                    payments_map[(key, c.id)] = {"montant_paye": montant, "prix": 0.0}
                    continue

                if statut == PAIEMENT_ANNULE_PERDU:
                    # Argent encaissé définitivement : ni participation ni crédit.
                    continue

                if not p.get("selectionne"):
                    continue
                key = p.get("adherent_id")
                if key is None:
                    continue
                students.setdefault(key, cls._bilan_student(p, adh.get(key)))
                participants_map[(key, c.id)] = statut
                payments_map[(key, c.id)] = {
                    "montant_paye": montant,
                    "prix": float(c.prix or 0.0),
                }

        seasons = sorted(
            {cls.season_of_date(c.date_competition) for c in comps if c.date_competition},
            reverse=True,
        )
        return {"competitions": comps, "students": students,
                "participations": participants_map, "payments": payments_map, "seasons": seasons}
