"""`adherents` directory: snapshot of the members of database.db on Firestore, read through a short cache."""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Sequence

from domain.constants import get_active_season
from domain.members import view as member_view
from domain.members.age_rules import age_at, get_season_start_date, parse_birth_date
from domain.members.purchase_priority import purchase_priority_score
from domain.members.sex import parse_sex
from domain.utils import normalize_string
from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.firestore.competitions import documents
from infrastructure.sqlite.connection import SqliteDatabase
from infrastructure.timed_cache import TimedCache

logger = logging.getLogger("alj")

_CACHE_SECONDS = 30.0
_CACHE_KEY = "adherents"


class _DirectoryState:
    """State of the directory in this process (one instance, `_state`)."""

    def __init__(self) -> None:
        # Any: directory documents as Firestore returns them
        self.cache: TimedCache[str, list[dict[str, Any]]] = TimedCache(_CACHE_SECONDS)
        # Last directory read: served again for a cache time when a refresh fails (_read_adherents)
        self.last_read: list[dict[str, Any]] | None = None
        # The outdated directory was already sent for rewriting by this process (_heal_outdated_directory)
        self.heal_requested = False
        # Waiting to be rewritten (CloudDatabase.refresh_projection reads it)
        self.outdated = False


_state = _DirectoryState()


def rebuild_member_directory(season_filter: str = "") -> dict[str, Any]:
    """Rebuilds the Firestore `adherents` directory from the main database.

    The mirror is rewritten in full (the Firestore directory reflects database.db), and the
    `planning` collection is updated along with it so that the PWA has the slot groups.
    Returns a report {imported, updated, errors}."""
    report: dict[str, Any] = {"imported": 0, "updated": 0, "errors": []}
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
                'SELECT * FROM v_member_flat WHERE season_name = ? '
                'ORDER BY "user_id" ASC', (season,)
            ).fetchall()
        if not rows:
            rows = main_conn.execute(
                'SELECT * FROM v_member_flat ORDER BY "user_id" ASC'
            ).fetchall()

        # Slot groups (planning -> tariffs) for the creneau_groupe field
        planning_groups = _read_planning_groups(main_conn)

        # `planning` collection (reference for the PWA)
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
                "path": f"{documents.COLLECTION_PLANNING}/{pr['id']}",
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
    now = documents.now_iso()
    adherent_writes = []
    for d in _best_purchase_rows(rows):
        adherent_id = d.get("user_id") or d.get("id")
        bdate = d.get("birth_date") or ""
        b_parsed = parse_birth_date(bdate)
        age_val = age_at(b_parsed, ref_date) if b_parsed else None
        t_name = str(d.get("tarif_name") or "").strip()
        groupe = planning_groups.get(normalize_string(t_name), "")
        licence = str(d.get("licence_ffme") or "").strip()
        adherent_writes.append({
            "path": f"{documents.COLLECTION_ADHERENTS}/{adherent_id}",
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

    invalidate_cache()
    _state.outdated = False
    report["updated"] = len(adherent_writes)
    return report


def _best_purchase_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """One row per member (the flat member view has one per purchase): the highest-priority purchase, by the
    import's rule (purchase_priority_score); on a tie the last row, as when every row was written in turn."""
    # adherent id -> (score, purchase row); Any: the ids come from SQLite rows
    best: dict[Any, tuple[int, dict[str, Any]]] = {}
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


def _read_planning_groups(main_conn: sqlite3.Connection) -> dict[str, str]:
    """{normalized tariff -> slot group} from the planning table (same rule as the member
    pages, domain.members.view: a tariff in two groups belongs to the first by id)."""
    try:
        rows = [dict(r) for r in main_conn.execute(
            "SELECT id, groupe, helloasso_tarifs FROM planning").fetchall()]
    except sqlite3.Error:
        logger.warning("Lecture des groupes de créneaux impossible : creneau_groupe laissé vide", exc_info=True)
        return {}
    return {k: slot["groupe"] for k, slot in member_view.tarif_slots(rows).items()}


def invalidate_cache() -> None:
    """Drops the cached directory: the next read goes to Firestore."""
    _state.cache.invalidate()
    _state.last_read = None


def adherents_raw() -> list[dict[str, Any]]:
    """The `adherents` directory documents, cached _CACHE_SECONDS seconds."""
    return _state.cache.get_or_load(_CACHE_KEY, _read_adherents)


def _read_adherents() -> list[dict[str, Any]]:
    """Reads the directory. A failed read keeps serving the last copy; with none yet, FirestoreError is raised
    (never an empty directory: it would look like a club without members, and is not cached)."""
    try:
        docs = FirestoreClient.list_documents(documents.COLLECTION_ADHERENTS)
    except Exception as e:
        logger.warning(f"[FIRESTORE] Lecture de l'annuaire adhérents impossible : {e}")
        if _state.last_read is not None:
            return _state.last_read
        if isinstance(e, FirestoreError):
            raise
        raise FirestoreError(f"Lecture de l'annuaire adhérents impossible : {e}") from e
    _heal_outdated_directory(docs)
    _state.last_read = docs
    return docs


def _heal_outdated_directory(docs: list[dict[str, Any]]) -> None:
    """A directory written before a field was added to it (`statut`, plans/competitor-status-filter.md) is marked
    outdated: CloudDatabase.refresh_projection rewrites it after the next write replicated to Firestore (it is
    built from the SQLite cache, which a read-only route may not have refreshed). Without it, the status filters
    would find nobody. Once per process: the sync never deletes, so the document of a member no longer synced
    keeps lacking the field."""
    if not _state.heal_requested and any("statut" not in doc for doc in docs):
        _state.outdated = True
        _state.heal_requested = True


def directory_outdated() -> bool:
    """Whether the directory waits to be rewritten (see _heal_outdated_directory)."""
    return _state.outdated


def adherent_map() -> dict[int, dict[str, Any]]:
    """{adherent id -> directory document}."""
    return {a["id"]: a for a in adherents_raw() if a.get("id") is not None}


def _adherent_as_legacy_dict(doc: dict[str, Any]) -> dict[str, Any]:
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
        "sex": sex_code(doc),
        "badge_rouge": str(doc.get("badge_rouge") or ""),
        "autonomie_bloc": str(doc.get("autonomie_bloc") or ""),
    }


def sex_code(doc: dict[str, Any]) -> str | None:
    """FFME code of a directory document; `gender`: documents written before the rename (plans/sex-enum.md),
    until the directory is next rewritten."""
    sex = parse_sex(doc.get("sex") if "sex" in doc else doc.get("gender"))
    return sex.value if sex else None


def list_members(search: str = "", competition_only: bool = False,
                 statuses: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Members of the Firestore directory (search ignores accents).
    `statuses`: only the members at one of these membership statuses (« Terminé »…); None: every status."""
    query = normalize_string(search) if search else ""
    result = []
    for doc in adherents_raw():
        member = _adherent_as_legacy_dict(doc)
        if competition_only and "competition" not in normalize_string(member.get("tarif") or ""):
            continue
        if statuses is not None and member["statut"] not in statuses:
            continue
        if query:
            haystack = normalize_string(
                f"{member.get('nom')} {member.get('prenom')} {member.get('num_licence')} {member.get('tarif')}"
            )
            if query not in haystack:
                continue
        result.append(member)
    return result
