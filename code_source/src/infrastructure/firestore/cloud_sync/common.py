"""Constantes, erreurs et conversions de valeurs communes à la réplication Firestore."""
import base64
import datetime
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from domain.members.sex import parse_sex

# Tables synchronisées (les tables legacy `adherents` / `adherents_seasons`,
# remplacées par le schéma v2, ne sont pas migrées).
TRACKED_TABLES = (
    "seasons", "users", "orders", "purchases", "purchase_options",
    "planning", "email_templates", "app_settings", "geocache",
)
COLLECTION_PREFIX = "crm_"
MOD_FIELD = "_modified_at"
DEL_FIELD = "_deleted"
BY_FIELD = "_modified_by"
META_FIELDS = (MOD_FIELD, DEL_FIELD, BY_FIELD)
# Bumped when a column changes: caches of an older format are rebuilt from Firestore (2: users.gender -> users.sex)
CACHE_FORMAT = "2"
PULL_MARGIN_SECONDS = 300
COMMIT_CHUNK = 400
# Références entre tables (pour renuméroter une ligne dont l'ID est déjà pris
# par un autre poste).
REFERENCES = {
    "seasons": [("orders", "season_id")],
    "users": [("purchases", "user_id")],
    "orders": [("purchases", "order_id")],
    "purchases": [("purchase_options", "purchase_id")],
}
DEFAULT_PROJECT_ID = "smart-amplifier-510811-n6"


class CloudSyncError(RuntimeError):
    """Échange impossible avec Firestore."""


class CloudConflictError(CloudSyncError):
    """Précondition refusée : le document a changé côté Firestore."""


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


# ----------------------------------------------------------------------
# Valeurs Firestore <-> SQLite (aller-retour exact : int, float, str, None, bytes)
# ----------------------------------------------------------------------
def encode_value(val: Any) -> Dict[str, Any]:
    if val is None:
        return {"nullValue": None}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, int):
        return {"integerValue": str(val)}
    if isinstance(val, float):
        if val != val:
            return {"doubleValue": "NaN"}
        if val in (float("inf"), float("-inf")):
            return {"doubleValue": "Infinity" if val > 0 else "-Infinity"}
        return {"doubleValue": val}
    if isinstance(val, (bytes, bytearray, memoryview)):
        return {"bytesValue": base64.b64encode(bytes(val)).decode("ascii")}
    return {"stringValue": str(val)}


def decode_value(f: Dict[str, Any]) -> Any:
    if not isinstance(f, dict) or "nullValue" in f:
        return None
    if "integerValue" in f:
        return int(f["integerValue"])
    if "doubleValue" in f:
        return float(f["doubleValue"])
    if "stringValue" in f:
        return f["stringValue"]
    if "booleanValue" in f:
        return bool(f["booleanValue"])
    if "bytesValue" in f:
        return base64.b64decode(f["bytesValue"])
    if "timestampValue" in f:
        return f["timestampValue"]
    return None


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

