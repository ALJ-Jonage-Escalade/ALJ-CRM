"""`adherents` directory: snapshot of the members of database.db, read through a short cache."""
import time
import json
from typing import Dict, Any, List, Optional, Sequence, Tuple

from domain.constants import get_active_season
from domain.members.age_rules import parse_birth_date, age_at, get_season_start_date
from domain.members import view as member_view
from domain.members.sex import parse_sex
from domain.utils import normalize_string
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions.base import CompetitionStoreBase
from infrastructure.sqlite.connection import SqliteDatabase
from domain.members.purchase_priority import purchase_priority_score

_ADHERENTS_CACHE_TTL = 30.0


class AdherentsMixin(CompetitionStoreBase):
    """Member directory: sync from the main database, cached reads, search."""

    _adherents_cache: Optional[List[Dict[str, Any]]] = None
    _adherents_cache_at: float = 0.0
    # The outdated directory was already sent for rewriting by this process (_heal_outdated_directory)
    _directory_heal_requested: bool = False

    # ------------------------------------------------------------------
    # Instantané des adhérents (source : database.db principale -> Firestore)
    # ------------------------------------------------------------------
    @classmethod
    def sync_adherents_from_main(cls, season_filter: str = "") -> dict:
        """Recalcule l'annuaire Firestore `adherents` depuis la base principale.

        Le miroir est intégralement réécrit (l'annuaire Firestore reflète
        database.db) et la collection `planning` est mise à jour dans la foulée
        pour que la PWA dispose des groupes de créneaux.
        Retourne un rapport {imported, updated, errors}.
        """
        report = {"imported": 0, "updated": 0, "errors": []}
        season = (season_filter or get_active_season() or "").strip()

        try:
            SqliteDatabase.setup_database()
            main_conn = SqliteDatabase.get_connection()
        except Exception as e:
            report["errors"].append(f"Base principale inaccessible : {e}")
            return report

        try:
            rows = []
            if season:
                rows = main_conn.execute(
                    'SELECT * FROM v_adherents_legacy WHERE season_name = ? '
                    'ORDER BY "user_id" ASC', (season,)
                ).fetchall()
            if not rows:
                rows = main_conn.execute(
                    'SELECT * FROM v_adherents_legacy ORDER BY "user_id" ASC'
                ).fetchall()

            # Groupes de créneaux (planning -> tarifs) pour le champ creneau_groupe
            planning_groups = cls._read_planning_groups(main_conn)

            # Collection planning (référence pour la PWA)
            planning_writes = []
            for pr in main_conn.execute(
                "SELECT * FROM planning ORDER BY jour, horaires"
            ).fetchall():
                enc = pr["encadrants"] or ""
                if enc.startswith("["):
                    try:
                        enc = ", ".join(json.loads(enc))
                    except (ValueError, TypeError):
                        pass
                planning_writes.append({
                    "path": f"{cls.COLLECTION_PLANNING}/{pr['id']}",
                    "data": {
                        "id": pr["id"],
                        "groupe": pr["groupe"] or "",
                        "type": pr["type"] or "",
                        "categorie_age": pr["categorie_age"] or "",
                        "jour": pr["jour"] or "",
                        "horaires": pr["horaires"] or "",
                        "encadrants": enc,
                    },
                })
        except Exception as e:
            report["errors"].append(f"Lecture de la base principale impossible : {e}")
            return report
        finally:
            main_conn.close()

        ref_date = get_season_start_date(season or get_active_season())
        now = cls._now_iso()
        adherent_writes = []
        for d in cls._best_purchase_rows(rows):
            adherent_id = d.get("user_id") or d.get("id")
            bdate = d.get("birth_date") or ""
            b_parsed = parse_birth_date(bdate)
            age_val = age_at(b_parsed, ref_date) if b_parsed else None
            t_name = str(d.get("tarif_name") or "").strip()
            groupe = planning_groups.get(normalize_string(t_name), "")
            licence = str(d.get("licence_ffme") or "").strip()
            adherent_writes.append({
                "path": f"{cls.COLLECTION_ADHERENTS}/{adherent_id}",
                "data": {
                    "id": adherent_id,
                    "nom": str(d.get("last_name") or "").strip().upper(),
                    "prenom": str(d.get("first_name") or "").strip().title(),
                    "licence_ffme": licence,
                    "num_licence": licence,
                    "birth_date": bdate,
                    "age": age_val,
                    "sex": d.get("sex"),
                    "email": str(d.get("email_primary") or "").strip(),
                    "email_secondaire": str(d.get("email_secondary") or "").strip(),
                    "phone": str(d.get("phone") or "").strip(),
                    "creneau_groupe": groupe,
                    "tarif": t_name,
                    "statut": member_view.normalize_status(d.get("status")),
                    "saison": str(d.get("season_name") or "").strip(),
                    "emergency_name": d.get("emergency1_name") or "",
                    "emergency_phone": d.get("emergency1_phone") or "",
                    "badge_rouge": d.get("badge_rouge") or "Non",
                    "autonomie_bloc": d.get("autonomie_bloc") or "Non",
                    "hid_proxkey": d.get("hid_proxkey") or "Non",
                    "hid_proxkey_date": d.get("hid_proxkey_date") or "",
                    "hid_proxkey_comment": d.get("hid_proxkey_comment") or "",
                    "updated_at": now,
                },
            })
            report["imported"] += 1

        writes = planning_writes + adherent_writes
        if writes:
            try:
                batch_report = FirestoreClient.batch_upsert(writes)
            except Exception as e:
                report["errors"].append(str(e))
                return report
            if batch_report["errors_count"]:
                report["errors"].append(
                    f"{batch_report['errors_count']} écriture(s) Firestore en échec : "
                    + " ; ".join(batch_report["errors"][:3])
                )
                report["updated"] = max(0, batch_report["written"] - len(planning_writes))
                return report

        cls._invalidate_adherents_cache()
        report["updated"] = len(adherent_writes)
        return report

    @staticmethod
    def _best_purchase_rows(rows: List[Any]) -> List[Dict[str, Any]]:
        """One row per member (`v_adherents_legacy` has one per purchase): the highest-priority purchase, by the
        import's rule (purchase_priority_score); on a tie the last row, as when every row was written in turn."""
        # adherent id -> (score, purchase row); Any: the ids come from SQLite rows
        best: Dict[Any, Tuple[int, Dict[str, Any]]] = {}
        for row in rows:
            purchase = dict(row)
            adherent_id = purchase.get("user_id") or purchase.get("id")
            if adherent_id is None:
                continue
            score = purchase_priority_score(purchase.get("status"), purchase.get("tarif_name"), purchase.get("amount"))
            kept = best.get(adherent_id)
            if kept is None or score >= kept[0]:
                best[adherent_id] = (score, purchase)
        return [purchase for _, purchase in best.values()]

    @staticmethod
    def _read_planning_groups(main_conn) -> Dict[str, str]:
        """{tarif normalisé -> groupe de créneau} depuis la table planning (same rule as the
        member pages, domain.members.view: a tariff in two groups belongs to the first by id)."""
        try:
            rows = [dict(r) for r in main_conn.execute(
                "SELECT id, groupe, helloasso_tarifs FROM planning").fetchall()]
        except Exception:
            return {}
        return {k: slot["groupe"] for k, slot in member_view.tarif_slots(rows).items()}

    @classmethod
    def list_planning_groups(cls) -> Dict[str, str]:
        """{tarif normalisé -> groupe de créneau} (lu directement dans database.db)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            return cls._read_planning_groups(conn)
        finally:
            conn.close()

    @classmethod
    def _invalidate_adherents_cache(cls):
        cls._adherents_cache = None
        cls._adherents_cache_at = 0.0

    @classmethod
    def _adherents_raw(cls) -> List[Dict[str, Any]]:
        """The `adherents` directory, cached _ADHERENTS_CACHE_TTL seconds. A failed read keeps
        serving the last copy; with none yet, FirestoreError is raised (never an empty
        directory: it would look like a club without members, and is not cached)."""
        now = time.time()
        if cls._adherents_cache is None or (now - cls._adherents_cache_at) > _ADHERENTS_CACHE_TTL:
            try:
                cls._adherents_cache = FirestoreClient.list_documents(cls.COLLECTION_ADHERENTS)
            except Exception as e:
                print(f"⚠️ [FIRESTORE] Lecture de l'annuaire adhérents impossible : {e}")
                if cls._adherents_cache is None:
                    if isinstance(e, FirestoreError):
                        raise
                    raise FirestoreError(f"Lecture de l'annuaire adhérents impossible : {e}") from e
            else:
                cls._heal_outdated_directory(cls._adherents_cache)
            cls._adherents_cache_at = now
        return cls._adherents_cache

    @classmethod
    def _heal_outdated_directory(cls, docs: List[Dict[str, Any]]) -> None:
        """A directory written before a field was added to it (`statut`, plans/competitor-status-filter.md) is
        rewritten by the next background tick: without it, the status filters would find nobody. Once per process:
        the sync never deletes, so the document of a member no longer synced keeps lacking the field."""
        if not cls._directory_heal_requested and any("statut" not in doc for doc in docs):
            from infrastructure.firestore.cloud_database import CloudDatabase
            CloudDatabase.mark_projection_dirty()
            cls._directory_heal_requested = True

    @classmethod
    def _adherent_map(cls) -> Dict[int, Dict[str, Any]]:
        return {a.get("id"): a for a in cls._adherents_raw() if a.get("id") is not None}

    @classmethod
    def _adherent_as_legacy_dict(cls, doc: Dict[str, Any]) -> Dict[str, Any]:
        licence = str(doc.get("licence_ffme") or doc.get("num_licence") or "")
        return {
            "id": doc.get("id"),
            "nom": str(doc.get("nom") or ""),
            "prenom": str(doc.get("prenom") or ""),
            "num_licence": licence,
            "email": str(doc.get("email") or ""),
            "email_secondaire": str(doc.get("email_secondaire") or ""),
            "phone": str(doc.get("phone") or ""),
            "tarif": str(doc.get("tarif") or ""),
            "statut": member_view.normalize_status(doc.get("statut")),
            "saison": str(doc.get("saison") or ""),
            "licence_ffme": licence,
            "creneau_groupe": str(doc.get("creneau_groupe") or ""),
            "emergency_name": str(doc.get("emergency_name") or ""),
            "emergency_phone": str(doc.get("emergency_phone") or ""),
            "birth_date": str(doc.get("birth_date") or ""),
            "age": doc.get("age"),
            "sex": cls._sex_code(doc),
            "badge_rouge": str(doc.get("badge_rouge") or ""),
            "autonomie_bloc": str(doc.get("autonomie_bloc") or ""),
            "hid_proxkey": str(doc.get("hid_proxkey") or ""),
            "hid_proxkey_date": str(doc.get("hid_proxkey_date") or ""),
            "hid_proxkey_comment": str(doc.get("hid_proxkey_comment") or ""),
        }

    @staticmethod
    def _sex_code(doc: Dict[str, Any]) -> Optional[str]:
        """FFME code of a directory document; `gender`: documents written before the rename (plans/sex-enum.md),
        until the directory is next rewritten."""
        sex = parse_sex(doc.get("sex") if "sex" in doc else doc.get("gender"))
        return sex.value if sex else None

    @classmethod
    def list_adherents(cls, search: str = "", competition_only: bool = False, statuses: Optional[Sequence[str]] = None) -> list:
        """Liste les adhérents de l'annuaire Firestore (recherche insensible aux accents).
        `statuses`: only the members at one of these membership statuses (« Terminé »…); None: every status."""
        q = normalize_string(search) if search else ""
        result = []
        for doc in cls._adherents_raw():
            d = cls._adherent_as_legacy_dict(doc)
            if competition_only and "competition" not in normalize_string(d.get("tarif") or ""):
                continue
            if statuses is not None and d["statut"] not in statuses:
                continue
            if q:
                haystack = normalize_string(
                    f"{d.get('nom')} {d.get('prenom')} {d.get('num_licence')} {d.get('tarif')}"
                )
                if q not in haystack:
                    continue
            result.append(d)
        return result

    @classmethod
    def count_adherents(cls) -> int:
        return len(cls._adherents_raw())
