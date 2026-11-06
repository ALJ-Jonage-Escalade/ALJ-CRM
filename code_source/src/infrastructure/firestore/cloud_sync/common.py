"""Constants and helpers of the Firestore replication (values and errors: infrastructure/firestore/client.py)."""
import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from domain.members.sex import parse_sex

# Tables synchronisées (les tables legacy `adherents` / `adherents_seasons`,
# remplacées par le schéma v2, ne sont pas migrées).
TRACKED_TABLES = (
    "seasons", "users", "emergency_contacts", "orders", "purchases", "purchase_options",
    "planning", "email_templates", "app_settings", "geocache",
    "keys", "key_assignments", "key_events",  # club keys, plans/club-keys.md
)
COLLECTION_PREFIX = "crm_"
MOD_FIELD = "_modified_at"
DEL_FIELD = "_deleted"
BY_FIELD = "_modified_by"
META_FIELDS = (MOD_FIELD, DEL_FIELD, BY_FIELD)
# Bumped when a column changes: caches of an older format are rebuilt from Firestore (2: users.gender -> users.sex, 3: emergency_contacts)
CACHE_FORMAT = "3"
PULL_MARGIN_SECONDS = 300
COMMIT_CHUNK = 400
# Références entre tables (pour renuméroter une ligne dont l'ID est déjà pris
# par un autre poste).
REFERENCES = {
    "seasons": [("orders", "season_id")],
    "users": [("purchases", "user_id"), ("emergency_contacts", "user_id"), ("key_assignments", "user_id")],
    "keys": [("key_assignments", "key_id"), ("key_events", "key_id")],
    "orders": [("purchases", "order_id")],
    "purchases": [("purchase_options", "purchase_id")],
}


def collection_for(table: str) -> str:
    return f"{COLLECTION_PREFIX}{table}"


def upgrade_legacy_fields(table: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Fields of a document written before a column was renamed, read under the new name.

    users.gender (free text) became users.sex (FFME code, plans/sex-enum.md): documents keep
    `gender` until scripts/migrate_gender_to_sex.py has run; a value not understood reads as None."""
    if table == "users" and "sex" not in fields and "gender" in fields:
        sex = parse_sex(fields["gender"])
        return {**fields, "sex": sex.value if sex else None}
    return fields


def quote_field_path(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "`" + name.replace("\\", "\\\\").replace("`", "\\`") + "`"


def doc_id_for(pk_values: List[Any]) -> str:
    """ID de document stable : la clé entière telle quelle, sinon une empreinte."""
    if len(pk_values) == 1 and isinstance(pk_values[0], int) and not isinstance(pk_values[0], bool):
        return str(pk_values[0])
    raw = json.dumps(pk_values, ensure_ascii=False, separators=(",", ":"))
    # sha1 kept on purpose: changing the hash would change the IDs of the existing Firestore documents
    return "h" + hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()  # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1


def ts_key(ts: Optional[str]) -> Tuple:
    """Clé de comparaison d'un horodatage RFC 3339 Firestore (précision ns)."""
    if not ts:
        return (0,)
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z", ts)
    if not m:
        return (ts,)
    frac = (m.group(2) or "").ljust(9, "0")[:9]
    return (m.group(1), frac)


def ts_minus(ts: str, seconds: int) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", ts or "")
    if not m:
        return "1970-01-01T00:00:00Z"
    dt = datetime.datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S") - datetime.timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _same(a: Any, b: Any) -> bool:
    return a == b and type(a) is type(b) or (a is None and b is None)

