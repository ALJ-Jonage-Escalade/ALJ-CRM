"""Copy of the two emergency contacts of `crm_users` into `crm_emergency_contacts`, plans/emergency-contacts.md phase 7.

Runs against PRODUCTION twice, around the deploy of release A: before it (the current code ignores the new collection),
then at once after it, for the members registered in between. Take a Firestore export first.

    uv run python scripts/migrate_emergency_contacts.py                 # dry run: report only, nothing written
    uv run python scripts/migrate_emergency_contacts.py --apply         # writes (asks to type the project id)
    uv run python scripts/migrate_emergency_contacts.py --emulator      # same against the emulator (dev/dev.env loaded)

Production access uses your own gcloud login (`gcloud auth login`, an account with Firestore access on the project),
not the club's OAuth refresh token: no secret has to be copied to this computer.

- For each member: contact 1 then contact 2, cleaned and without the same person twice; `position` 0, 1; ids after the
  highest in the collection. `crm_users` is never written.
- A member with any document in the collection, tombstones included, is skipped: a second run cannot restore contacts
  an admin has just removed. A write that finds its id taken (by an instance) is retried on a new id.

The report gives, by user id and order refs (no names, no phones): the members whose first contact is blank (the second
one becomes the main one, so their FFME export changes), and those whose rows differ from the old columns (edits made
between the copy and the deploy: fix them by hand in the app).
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess  # noqa: S404 - runs the gcloud CLI, fixed arguments
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from domain.members.emergency_contacts import EmergencyContact, clean_contacts, missing_contacts  # noqa: E402
from infrastructure import runtime_env  # noqa: E402
from infrastructure.firestore.client import FirestoreConflictError  # noqa: E402
from infrastructure.firestore.cloud_sync.common import COMMIT_CHUNK, collection_for  # noqa: E402
from infrastructure.firestore.cloud_sync.rest_store import RestStore  # noqa: E402

# Any in this script: fields and ids as read from Firestore documents, which RestStore does not type
CONTACTS = collection_for("emergency_contacts")
MAX_ATTEMPTS = 5
GCLOUD_TOKEN_LIFETIME = 45 * 60  # seconds; gcloud's access tokens last 1 hour


class GcloudToken:
    """Access tokens of the account logged in with `gcloud auth login`, renewed before they expire."""

    def __init__(self) -> None:
        self._token = ""
        self._fetched_at = 0.0

    def __call__(self) -> str:
        if not self._token or time.monotonic() - self._fetched_at > GCLOUD_TOKEN_LIFETIME:
            self._token = gcloud_access_token()
            self._fetched_at = time.monotonic()
        return self._token


def gcloud_access_token() -> str:
    gcloud = shutil.which("gcloud")
    if not gcloud:
        sys.exit("gcloud introuvable : installez le Google Cloud CLI puis lancez `gcloud auth login`.")
    result = subprocess.run([gcloud, "auth", "print-access-token"], capture_output=True, text=True, check=False)  # noqa: S603 - fixed arguments
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        sys.exit(f"Jeton gcloud indisponible, lancez `gcloud auth login` : {result.stderr.strip()}")
    return token


@dataclass
class Report:
    by_count: Counter[int] = field(default_factory=Counter)  # number of contacts copied -> members
    duplicates: int = 0
    skipped: int = 0
    first_contact_blank: Dict[Any, str] = field(default_factory=dict)  # user id -> order refs
    different: Dict[Any, str] = field(default_factory=dict)  # user id -> order refs


def old_rows(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"name": fields.get(f"emergency{number}_name"), "phone": fields.get(f"emergency{number}_phone")} for number in (1, 2)]


def order_refs_by_user(store: RestStore) -> Dict[Any, str]:
    """{user id -> order refs}, from crm_purchases and crm_orders (crm_users holds no order ref)."""
    orders = {d["fields"].get("id"): d["fields"].get("order_ref") for d in store.list_all(collection_for("orders")) if not d["deleted"]}
    refs: Dict[Any, List[str]] = {}
    for d in store.list_all(collection_for("purchases")):
        ref = orders.get(d["fields"].get("order_id"))
        if ref and not d["deleted"]:
            refs.setdefault(d["fields"].get("user_id"), []).append(str(ref))
    return {user_id: ", ".join(values) for user_id, values in refs.items()}


def existing_contacts(store: RestStore) -> Tuple[Set[Any], Dict[Any, List[EmergencyContact]]]:
    """Users with any document in the collection, tombstones included, and the live rows of each, in order."""
    owners: Set[Any] = set()
    rows: Dict[Any, List[Dict[str, Any]]] = {}
    for doc in store.list_all(CONTACTS):
        owner = doc["fields"].get("user_id")
        owners.add(owner)
        if not doc["deleted"]:
            rows.setdefault(owner, []).append(doc["fields"])
    live = {owner: clean_contacts(sorted(values, key=lambda row: row.get("position") or 0)) for owner, values in rows.items()}
    return owners, live


def write_contacts(store: RestStore, to_copy: List[Tuple[Any, int, EmergencyContact]]) -> None:
    """Writes the rows by chunks, on ids read just before each one; a chunk that finds an id taken is retried."""
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    for start in range(0, len(to_copy), COMMIT_CHUNK):
        chunk = to_copy[start:start + COMMIT_CHUNK]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            first_id = store.max_int_id(CONTACTS, "id") + 1
            writes = [{
                "collection": CONTACTS, "doc_id": str(first_id + offset), "by": "migration contacts", "mask": None, "deleted": False,
                "precondition": {"exists": False},
                "fields": {"id": first_id + offset, "user_id": user_id, "name": contact.name, "phone": contact.phone,
                           "position": position, "created_at": now_iso, "updated_at": now_iso},
            } for offset, (user_id, position, contact) in enumerate(chunk)]
            try:
                store.commit(writes)
                break
            except FirestoreConflictError:
                if attempt == MAX_ATTEMPTS:
                    raise SystemExit(f"Identifiants toujours pris après {MAX_ATTEMPTS} essais : relancez le script.") from None


def migrate(store: RestStore, apply: bool, report: Report) -> None:
    owners, live = existing_contacts(store)
    to_copy: List[Tuple[Any, int, EmergencyContact]] = []
    blank_first: List[Any] = []  # Any: user ids as stored in Firestore
    different: List[Any] = []
    for doc in store.list_all(collection_for("users")):
        if doc["deleted"]:
            continue
        fields = doc["fields"]
        user_id = fields.get("id")
        wanted = missing_contacts([], old_rows(fields))
        if user_id in owners:
            report.skipped += 1
            if live.get(user_id, []) != wanted:
                different.append(user_id)
            continue
        cleaned = clean_contacts(old_rows(fields))
        report.duplicates += len(cleaned) - len(wanted)
        report.by_count[len(wanted)] += 1
        if cleaned and not str(fields.get("emergency1_name") or "").strip() and not str(fields.get("emergency1_phone") or "").strip():
            blank_first.append(user_id)
        to_copy += [(user_id, position, contact) for position, contact in enumerate(wanted)]
    if blank_first or different:
        refs = order_refs_by_user(store)
        report.first_contact_blank = {user_id: refs.get(user_id, "aucune commande") for user_id in blank_first}
        report.different = {user_id: refs.get(user_id, "aucune commande") for user_id in different}
    if apply:
        write_contacts(store, to_copy)


def print_report(report: Report, apply: bool) -> None:
    verb = "copiés" if apply else "à copier"
    print(f"\nAdhérents {verb} : {sum(report.by_count.values())} (déjà présents dans la collection, inchangés : {report.skipped})")
    for count, members in sorted(report.by_count.items()):
        print(f"  {count} contact(s) : {members} adhérent(s)")
    print(f"  Doublons retirés : {report.duplicates}")
    if report.first_contact_blank:
        print(f"\n⚠️ {len(report.first_contact_blank)} adhérent(s) sans contact 1 mais avec un contact 2 : leur export FFME change.")
        for user_id, refs in sorted(report.first_contact_blank.items(), key=lambda item: str(item[0])):
            print(f"  user {user_id} — commandes : {refs}")
    if report.different:
        print(f"\n⚠️ {len(report.different)} adhérent(s) dont les contacts diffèrent des anciennes colonnes : à vérifier dans la fiche.")
        for user_id, refs in sorted(report.different.items(), key=lambda item: str(item[0])):
            print(f"  user {user_id} — commandes : {refs}")
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
    store = RestStore() if emulator else RestStore(token_provider=GcloudToken())
    target = f"émulateur {emulator}" if emulator else "PRODUCTION"
    print(f"Projet Firestore : {store.project_id} ({target})")
    if args.apply and not emulator:
        typed = input(f"Écriture en production : tapez l'identifiant du projet ({store.project_id}) pour confirmer : ")
        if typed.strip() != store.project_id:
            print("Confirmation incorrecte : rien n'a été écrit.", file=sys.stderr)
            return 1

    report = Report()
    migrate(store, args.apply, report)
    print_report(report, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
