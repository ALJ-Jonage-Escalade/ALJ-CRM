"""One-shot migration `gender` (free text) -> `sex` (FFME code "F" / "H"), plans/sex-enum.md phase 7.

Runs against PRODUCTION after the deploy of the version that reads `sex` (it reads `gender` as a fallback
meanwhile). Take a Firestore export first: it is the only way back once the `gender` fields are deleted.

    uv run python scripts/migrate_gender_to_sex.py                 # dry run: report only, nothing written
    uv run python scripts/migrate_gender_to_sex.py --apply         # writes (asks to type the project id)
    uv run python scripts/migrate_gender_to_sex.py --emulator      # same against the emulator (dev/dev.env loaded)

- `crm_users`: `sex` = the existing `sex`, else parse_sex(`gender`) (None when not understood); `gender` deleted.
  Written like the cache sync (precondition on the version read, `_modified_at` bumped so instances pull it).
- `competitions`: the copy of `gender` in each participant row is removed (the view reads the member's sex).
- `adherents` (directory): `gender` replaced by `sex` on the documents the projection no longer rewrites.

Re-runnable: a document without `gender` is left alone. The report gives counts per resulting value and the
members whose value was not understood, by user id and order refs (no names), to fix by hand in the app.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from domain.members.sex import parse_sex  # noqa: E402
from infrastructure import runtime_env  # noqa: E402
from infrastructure.firestore.client import FirestoreClient  # noqa: E402
from infrastructure.firestore.cloud_sync.common import COMMIT_CHUNK, collection_for  # noqa: E402
from infrastructure.firestore.cloud_sync.rest_store import RestStore  # noqa: E402
from infrastructure.firestore.competitions import participants  # noqa: E402
from infrastructure.firestore.competitions import member_directory  # noqa: E402
from infrastructure.firestore.competitions import documents  # noqa: E402

LEGACY = "gender"
NOT_GIVEN = "(non renseigné)"


@dataclass
class UserChange:
    doc_id: str
    update_time: Optional[str]
    sex: Optional[str]


@dataclass
class Report:
    users_by_sex: Counter[str] = field(default_factory=Counter)
    unparsed: Dict[Any, str] = field(default_factory=dict)  # user id -> order refs
    users_skipped: int = 0
    participants: int = 0
    competitions: int = 0
    directory: int = 0


def user_change(doc: Dict[str, Any]) -> Optional[UserChange]:
    """The write for a `crm_users` document (RestStore format), None when it holds no `gender`."""
    fields = doc["fields"]
    if doc.get("deleted") or LEGACY not in fields:
        return None
    if "sex" in fields:  # written by the new version since (record edited): it wins
        sex = parse_sex(fields["sex"])
    else:
        sex = parse_sex(fields[LEGACY])
    return UserChange(doc["id"], doc.get("update_time"), sex.value if sex else None)


def without_gender(rows: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """The participant rows without their copied `gender`, None when none holds one (nothing to write)."""
    if not any(LEGACY in row for row in rows):
        return None
    return [{k: v for k, v in row.items() if k != LEGACY} for row in rows]


def order_refs_by_user(store: RestStore) -> Dict[Any, List[str]]:
    """{user id -> order refs}, from crm_purchases and crm_orders (crm_users holds no order ref)."""
    orders = {d["fields"].get("id"): d["fields"].get("order_ref") for d in store.list_all(collection_for("orders")) if not d["deleted"]}
    refs: Dict[Any, List[str]] = {}
    for d in store.list_all(collection_for("purchases")):
        if d["deleted"]:
            continue
        ref = orders.get(d["fields"].get("order_id"))
        if ref:
            refs.setdefault(d["fields"].get("user_id"), []).append(str(ref))
    return refs


def migrate_users(store: RestStore, apply: bool, report: Report) -> None:
    docs = store.list_all(collection_for("users"))
    changes: List[UserChange] = []
    unparsed_ids: List[Any] = []  # Any: user ids as stored in Firestore
    for doc in docs:
        change = user_change(doc)
        if change is None:
            report.users_skipped += 1
            continue
        changes.append(change)
        report.users_by_sex[change.sex or NOT_GIVEN] += 1
        if change.sex is None and str(doc["fields"].get(LEGACY) or "").strip():
            unparsed_ids.append(doc["fields"].get("id"))
    if unparsed_ids:
        refs = order_refs_by_user(store)
        report.unparsed = {uid: ", ".join(refs.get(uid, [])) or "aucune commande" for uid in unparsed_ids}
    if not apply:
        return
    writes = [{
        "collection": collection_for("users"), "doc_id": c.doc_id, "by": "migration sex",
        "fields": {"sex": c.sex}, "mask": ["sex", LEGACY],  # in the mask, absent from the fields: deleted
        "precondition": {"updateTime": c.update_time} if c.update_time else {"exists": True},
    } for c in changes]
    for start in range(0, len(writes), COMMIT_CHUNK):
        store.commit(writes[start:start + COMMIT_CHUNK])


def migrate_competitions(apply: bool, report: Report) -> None:
    for doc in FirestoreClient.list_documents(documents.COLLECTION_COMPETITIONS):
        rows = doc.get("participants") or []
        if without_gender(rows) is None:
            continue
        report.competitions += 1
        report.participants += sum(1 for row in rows if LEGACY in row)
        if apply:
            if doc.get("id") is None:
                raise SystemExit(f"Compétition sans identifiant (document {doc.get('_doc_id')}) : ouvrez-la dans l'application puis relancez.")
            # Re-read and retried on a concurrent write; participant `updated_at` untouched (offline guards)
            participants.mutate_participants(doc["id"], without_gender)


def migrate_directory(apply: bool, report: Report) -> None:
    writes = []
    for doc in FirestoreClient.list_documents(documents.COLLECTION_ADHERENTS):
        if LEGACY not in doc:
            continue
        report.directory += 1
        writes.append({"path": f"{documents.COLLECTION_ADHERENTS}/{doc['_doc_id']}",
                       "data": {"sex": member_directory.sex_code(doc)}, "update_fields": ["sex", LEGACY]})
    if apply and writes:
        result = FirestoreClient.batch_upsert(writes)
        if result["errors_count"]:
            raise SystemExit(f"Annuaire : {result['errors_count']} écriture(s) en échec : {result['errors'][:3]}")


def print_report(report: Report, apply: bool) -> None:
    verb = "migrés" if apply else "à migrer"
    print(f"\ncrm_users {verb} : {sum(report.users_by_sex.values())} (sans `{LEGACY}`, inchangés : {report.users_skipped})")
    for value, count in sorted(report.users_by_sex.items()):
        print(f"  sex = {value} : {count}")
    if report.unparsed:
        print(f"\n⚠️ {len(report.unparsed)} valeur(s) non reconnue(s), à corriger dans la fiche de l'adhérent :")
        for user_id, refs in sorted(report.unparsed.items(), key=lambda item: str(item[0])):
            print(f"  user {user_id} — commandes : {refs}")
    print(f"\ncompetitions : {report.participants} participant(s) {verb} dans {report.competitions} compétition(s)")
    print(f"adherents (annuaire) : {report.directory} document(s) {verb}")
    if not apply:
        print("\nSimulation : rien n'a été écrit. Relancez avec --apply pour écrire.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
    migrate_users(store, args.apply, report)
    migrate_competitions(args.apply, report)
    migrate_directory(args.apply, report)
    print_report(report, args.apply)
    return 0


if __name__ == "__main__":
    runtime_env.load_env_files()  # .env files as the server reads them (never at import: tests call main())
    sys.exit(main())
