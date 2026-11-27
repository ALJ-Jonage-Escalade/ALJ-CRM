"""One-shot migration: the FFME category of the members already imported (plans/ffme-categories.md D10).

Runs against PRODUCTION after the deploy of the version that reads `ffme_category`. Take a Firestore export first: it
is the only way back once the participants' `categorie_ffme` is deleted. Delete this script and its test once it ran.

    uv run python scripts/migrate_ffme_category.py                 # dry run: report only, nothing written
    uv run python scripts/migrate_ffme_category.py --apply         # writes (asks to type the project id)
    uv run python scripts/migrate_ffme_category.py --emulator      # same against the emulator (dev/dev.env loaded)

- `crm_users`: `ffme_category` = the category of the birth date for the season of the member's latest membership
  ("" without birth date or membership). Written like the cache sync (precondition on the version read, `_modified_at`
  bumped so instances pull it). A member that already has a category (imported or edited since) is left alone.
- `competitions`: each participant row gets `categorie`, computed for the competition's own season (from its date:
  the category it was entered in), and loses the MyCompet `categorie_ffme`. Undated competition or unknown member: "".
- `adherents` (directory): `ffme_category` set on the documents that have none.

An empty value counts as missing: between the deploy and this run, the SQLite column default ('') reaches Firestore
(a member edited, the directory rebuilt) and participants added meanwhile copy it; they are computed like the others.
Only a value that changes something is written (an empty one stays when the computed category is empty too).

Re-runnable. The report gives counts per category and the members not computed, by user id (no names).
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from domain.members.age_rules import parse_birth_date  # noqa: E402
from domain.members.ffme_category import category_for  # noqa: E402
from infrastructure import runtime_env  # noqa: E402
from infrastructure.firestore.client import FirestoreClient  # noqa: E402
from infrastructure.firestore.cloud_sync.common import COMMIT_CHUNK, collection_for  # noqa: E402
from infrastructure.firestore.cloud_sync.rest_store import RestStore  # noqa: E402
from infrastructure.firestore.competitions import documents, participants  # noqa: E402

FIELD = "ffme_category"
LEGACY = "categorie_ffme"
NONE = "(aucune)"


@dataclass
class Report:
    users_by_category: Counter[str] = field(default_factory=Counter)
    not_computed: List[Any] = field(default_factory=list)  # user ids (Any: as stored in Firestore)
    users_skipped: int = 0
    participants: int = 0
    competitions: int = 0
    directory: int = 0


def _live(store: RestStore, table: str) -> List[Dict[str, Any]]:  # Any: Firestore values
    return [doc["fields"] for doc in store.list_all(collection_for(table)) if not doc.get("deleted")]


def latest_seasons(store: RestStore) -> Dict[Any, str]:
    """{user id -> name of the season of their most recent membership}, from crm_purchases ⨝ crm_orders ⨝ crm_seasons."""
    season_names = {s.get("id"): str(s.get("name") or "") for s in _live(store, "seasons")}
    order_seasons = {o.get("id"): season_names.get(o.get("season_id"), "") for o in _live(store, "orders")}
    latest: Dict[Any, str] = {}
    for purchase in _live(store, "purchases"):
        season = order_seasons.get(purchase.get("order_id"), "")
        user_id = purchase.get("user_id")
        if season and season > latest.get(user_id, ""):
            latest[user_id] = season
    return latest


def birth_dates(store: RestStore) -> Dict[Any, Optional[datetime.date]]:
    return {u.get("id"): parse_birth_date(u.get("birth_date")) for u in _live(store, "users")}


def _computed(birth: Optional[datetime.date], season: Optional[str]) -> str:
    """The category code for that season, "" when none (no birth date, no season, under 9)."""
    category = category_for(birth, season) if season else None
    return category.value if category else ""


def _needs_write(stored: Dict[str, Any], key: str, computed: str) -> bool:
    """A missing key, or an empty one the computed category fills; a non-empty value is kept (set by the app since)."""
    return key not in stored or (not stored[key] and bool(computed))


def member_categories(store: RestStore) -> Dict[Any, str]:
    """{user id -> category}: the stored one, else the one computed for their latest season ("" when none)."""
    seasons = latest_seasons(store)
    result: Dict[Any, str] = {}
    for user in _live(store, "users"):
        user_id = user.get("id")
        stored = str(user.get(FIELD) or "")
        result[user_id] = stored or _computed(parse_birth_date(user.get("birth_date")), seasons.get(user_id))
    return result


def migrate_users(store: RestStore, apply: bool, report: Report) -> None:
    seasons = latest_seasons(store)
    writes = []
    for doc in store.list_all(collection_for("users")):
        fields = doc["fields"]
        user_id = fields.get("id")
        birth, season = parse_birth_date(fields.get("birth_date")), seasons.get(user_id)
        category = _computed(birth, season)
        if doc.get("deleted") or not _needs_write(fields, FIELD, category):
            report.users_skipped += 1
            continue
        report.users_by_category[category or NONE] += 1
        if birth is None or season is None:
            report.not_computed.append(user_id)
        writes.append({
            "collection": collection_for("users"), "doc_id": doc["id"], "by": "migration ffme_category",
            "fields": {FIELD: category}, "mask": [FIELD],
            "precondition": {"updateTime": doc["update_time"]} if doc.get("update_time") else {"exists": True},
        })
    if apply:
        for start in range(0, len(writes), COMMIT_CHUNK):
            store.commit(writes[start:start + COMMIT_CHUNK])


def season_of(day: str) -> Optional[str]:
    """The season of a YYYY-MM-DD date (1 September switch), None when the date cannot be read."""
    try:
        date = datetime.date.fromisoformat(day[:10])
    except ValueError:
        return None
    start = date.year if date.month >= 9 else date.year - 1
    return f"{start}-{start + 1}"


def _participant_category(row: Dict[str, Any], births: Dict[Any, Optional[datetime.date]], season: Optional[str]) -> str:
    return _computed(births.get(row.get("adherent_id")), season)


def _needs_migration(row: Dict[str, Any], births: Dict[Any, Optional[datetime.date]], season: Optional[str]) -> bool:
    return LEGACY in row or _needs_write(row, "categorie", _participant_category(row, births, season))


def migrate_competitions(store: RestStore, apply: bool, report: Report) -> None:
    births = birth_dates(store)
    for doc in FirestoreClient.list_documents(documents.COLLECTION_COMPETITIONS):
        rows = doc.get("participants") or []
        season = season_of(str(doc.get("date_competition") or ""))
        pending = sum(1 for row in rows if _needs_migration(row, births, season))
        if not pending:
            continue
        report.competitions += 1
        report.participants += pending
        if not apply:
            continue
        if doc.get("id") is None:
            raise SystemExit(f"Compétition sans identifiant (document {doc.get('_doc_id')}) : ouvrez-la dans l'application puis relancez.")

        def migrated(current: List[Dict[str, Any]], season: Optional[str] = season) -> Optional[List[Dict[str, Any]]]:
            if not any(_needs_migration(row, births, season) for row in current):
                return None
            out = []
            for row in current:
                if not _needs_migration(row, births, season):
                    out.append(row)
                    continue
                kept = {k: v for k, v in row.items() if k != LEGACY}
                if not kept.get("categorie"):
                    kept["categorie"] = _participant_category(row, births, season)
                out.append(kept)
            return out
        # Re-read and retried on a concurrent write; participant `updated_at` untouched (offline guards)
        participants.mutate_participants(doc["id"], migrated)


def migrate_directory(store: RestStore, apply: bool, report: Report) -> None:
    categories = member_categories(store)
    writes = []
    for doc in FirestoreClient.list_documents(documents.COLLECTION_ADHERENTS):
        category = categories.get(doc.get("id"), "")
        if not _needs_write(doc, FIELD, category):
            continue
        report.directory += 1
        writes.append({"path": f"{documents.COLLECTION_ADHERENTS}/{doc['_doc_id']}",
                       "data": {FIELD: category}, "update_fields": [FIELD]})
    if apply and writes:
        result = FirestoreClient.batch_upsert(writes)
        if result["errors_count"]:
            raise SystemExit(f"Annuaire : {result['errors_count']} écriture(s) en échec : {result['errors'][:3]}")


def print_report(report: Report, apply: bool) -> None:
    verb = "migrés" if apply else "à migrer"
    print(f"\ncrm_users {verb} : {sum(report.users_by_category.values())} (déjà renseignés, inchangés : {report.users_skipped})")
    for value, count in sorted(report.users_by_category.items()):
        print(f"  {FIELD} = {value} : {count}")
    if report.not_computed:
        print(f"\n⚠️ {len(report.not_computed)} adhérent(s) sans date de naissance ou sans adhésion (catégorie vide) :")
        print("  users " + ", ".join(str(user_id) for user_id in sorted(report.not_computed, key=str)))
    print(f"\ncompetitions : {report.participants} participant(s) {verb} dans {report.competitions} compétition(s)")
    print(f"adherents (annuaire) : {report.directory} document(s) {verb}")
    if not apply:
        print("\nSimulation : rien n'a été écrit. Relancez avec --apply pour écrire.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--emulator", action="store_true", help="allow the Firestore emulator (FIRESTORE_EMULATOR_HOST)")
    args = parser.parse_args(argv)

    emulator = runtime_env.firestore_emulator_host()
    if os.environ.get("FIRESTORE_EMULATOR_HOST") and not emulator:
        # The emulator is only used in dev mode: without ALJ_ENV=dev this would silently target production
        print("FIRESTORE_EMULATOR_HOST défini sans ALJ_ENV=dev : environnement incohérent, chargez dev/dev.env "
              "(émulateur) ou retirez la variable (production).", file=sys.stderr)
        return 2
    if emulator and not args.emulator:
        print(f"FIRESTORE_EMULATOR_HOST={emulator} : ajoutez --emulator pour migrer l'émulateur.", file=sys.stderr)
        return 2
    if args.emulator and not emulator:
        print("--emulator sans FIRESTORE_EMULATOR_HOST : chargez dev/dev.env.", file=sys.stderr)
        return 2
    store = RestStore()
    target = f"émulateur {emulator}" if emulator else "PRODUCTION"
    print(f"Projet Firestore : {store.project_id} ({target})")
    if args.apply and not emulator:
        typed = input(f"Écriture en production : tapez l'identifiant du projet ({store.project_id}) pour confirmer : ")
        if typed.strip() != store.project_id:
            print("Confirmation incorrecte : rien n'a été écrit.", file=sys.stderr)
            return 1

    report = Report()
    # Competitions and directory first: they read the members' birth dates and categories as they are now
    migrate_competitions(store, args.apply, report)
    migrate_directory(store, args.apply, report)
    migrate_users(store, args.apply, report)
    print_report(report, args.apply)
    return 0


if __name__ == "__main__":
    runtime_env.load_env_files()  # .env files as the server reads them (never at import: tests call main())
    sys.exit(main())
