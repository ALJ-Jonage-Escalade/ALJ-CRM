"""
Schéma cible v2 (users / orders / purchases / purchase_options) — module partagé.

Source unique de vérité pour :
- le DDL des tables v2 (migration et écritures applicatives),
- les normalisations (statuts, dates, textes legacy NULL/'' ),
- la table de priorité des statuts,
- les upserts users / orders / purchases / purchase_options.

Importé par infrastructure.sqlite.members et infrastructure.sqlite.connection.
Aucune dépendance à infrastructure.sqlite.connection pour éviter toute importation circulaire.
"""
import datetime
import logging
import sqlite3
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from domain.members.age_rules import parse_birth_date
from domain.members.ffme_category import category_for
from domain.members.helloasso_membership import INSURANCE_OPTIONS
from domain.members.emergency_contacts import HELLOASSO_CONTACT_FIELDS, EmergencyContact, missing_contacts
from domain.members.purchase_priority import purchase_priority_score, status_score
from domain.members.sex import parse_sex
from domain.members.view import normalize_status
from domain.utils import normalize_name

logger = logging.getLogger("alj")

# A member record: a flat HelloAsso export row (dict) or a SQLite row. Any: values of many columns and types
MemberRecord = Union[Mapping[str, Any], sqlite3.Row]

SCHEMA_TARGET_VERSION = 2


V2_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name_key TEXT NOT NULL,
    first_name_key TEXT NOT NULL,
    birth_date TEXT,
    birth_date_raw TEXT,
    sex TEXT, nationality TEXT,
    address TEXT, zip_code TEXT, city TEXT, country TEXT,
    phone TEXT,
    email_primary TEXT, email_secondary TEXT,
    emergency1_name TEXT, emergency1_phone TEXT,
    emergency2_name TEXT, emergency2_phone TEXT,
    licence_ffme TEXT,
    ffme_category TEXT DEFAULT '',
    photo_auth TEXT, health_commitment TEXT,
    badge_rouge TEXT DEFAULT 'Non',
    autonomie_bloc TEXT DEFAULT 'Non',
    raw_passports TEXT DEFAULT '',
    raw_diplomas TEXT DEFAULT '',
    parental_auth_autonomous TEXT DEFAULT 'Non',
    parental_auth_family TEXT DEFAULT 'Non',
    legacy_adherent_id INTEGER UNIQUE,
    created_at TEXT, updated_at TEXT,
    UNIQUE(last_name_key, first_name_key, birth_date)
);
CREATE INDEX IF NOT EXISTS idx_users_names ON users(last_name_key, first_name_key);

CREATE TABLE IF NOT EXISTS emergency_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_emergency_contacts_user ON emergency_contacts(user_id, position);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ref TEXT UNIQUE NOT NULL,
    order_date TEXT,
    status TEXT,
    status_normalized TEXT,
    payment_method TEXT,
    payer_last_name TEXT, payer_first_name TEXT, payer_email TEXT,
    promo_code TEXT, promo_amount REAL,
    comment TEXT,
    season_id INTEGER REFERENCES seasons(id),
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_season ON orders(season_id);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    tarif_name TEXT, amount REAL,
    status TEXT, status_normalized TEXT,
    is_tribe TEXT DEFAULT 'Non',
    email_sent_date TEXT,
    is_modified TEXT DEFAULT 'Non',
    commentaires_correctif TEXT DEFAULT '',
    document_sante TEXT DEFAULT '',
    helloasso_item_id INTEGER, helloasso_status TEXT, helloasso_amount REAL, helloasso_tarif TEXT,
    legacy_adherent_id INTEGER,
    legacy_season_id INTEGER,
    created_at TEXT, updated_at TEXT,
    UNIQUE(order_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_purchases_order ON purchases(order_id);

CREATE TABLE IF NOT EXISTS purchase_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    option_name TEXT NOT NULL,
    amount REAL DEFAULT 0.0,
    UNIQUE(purchase_id, option_name)
);
"""

# Colonnes legacy adherents -> colonnes users (libellés courts certains)
USER_FIELD_MAP = {
    "user_lastName": "last_name",
    "user_firstName": "first_name",
    "champ_Sexe": "sex",
    "champ_Nationalité": "nationality",
    "champ_Adresse : numéro et nom de rue": "address",
    "champ_Code postal": "zip_code",
    "champ_Ville": "city",
    "champ_Pays": "country",
    "champ_Téléphone ": "phone",
    "champ_Adresse mail pour la réception des informations du club": "email_primary",
    "champ_Deuxième adresse mail pour la réception des informations du club": "email_secondary",
    "champ_Numéro de Licence FFME (6 chiffres)": "licence_ffme",
    "badge_rouge": "badge_rouge",
    "autonomie_bloc": "autonomie_bloc",
    "raw_passports": "raw_passports",
    "raw_diplomas": "raw_diplomas",
    "parental_auth_autonomous": "parental_auth_autonomous",
    "parental_auth_family": "parental_auth_family",
}

# Colonnes à très longs libellés : résolues dynamiquement via PRAGMA table_info
DYNAMIC_USER_FIELDS = [
    ("champ_En cas de prise de vue", "photo_auth"),
    ("champ_Je m'engage", "health_commitment"),
]

DOB_COLUMN = "champ_Date de naissance de l'adhérent"

# (nom d'option cible, colonne has legacy, colonne montant legacy)
# (option, "has it" column, amount column) of the flat format, one per insurance of the club's list
OPTION_PAIRS = [(option, f"opt_{option}", f"opt_Montant {option}") for option in INSURANCE_OPTIONS]


def clean_legacy_text(val: object) -> Optional[str]:
    """
    Préserve la distinction NULL / chaîne vide du legacy : le générateur CSV historique
    applique str(None) ('None') sur les valeurs NULL — les restituer telles quelles
    garantit un export octet-pour-octet identique.
    """
    if val is None:
        return None
    return str(val).strip()


def sex_code(raw: object, order_ref: object) -> str | None:
    """Value of the users.sex column (FFME code "F" / "H") for an imported value (HelloAsso, Excel, legacy).

    A value not understood is stored as NULL and logged with its order (never the member's name)."""
    sex = parse_sex(raw)
    if sex is None and str(raw or "").strip():
        logger.warning("Sexe non reconnu pour la commande %s : enregistré comme non renseigné", order_ref)
    return sex.value if sex else None


def legacy_date_to_iso(val: object) -> str:
    """Normalise une date legacy ('20/08/2012', '2012-08-20T00:00:00', ...) en ISO '2012-08-20'."""
    s = str(val or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%y"):
        try:
            dt = datetime.datetime.strptime(s[:19] if "T" in s else s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def is_true(val: object) -> bool:
    return str(val or "").strip().lower() in ("oui", "true", "vrai", "1", "yes")


def _get(rec: MemberRecord, key: str) -> Any:  # Any: a stored or HelloAsso value of any column
    """Accès tolérant : fonctionne avec les dict HelloAsso et les sqlite3.Row."""
    try:
        return rec[key]
    except (KeyError, IndexError):
        return None


def build_user_field_map(cur: Optional[sqlite3.Cursor] = None) -> Dict[str, str]:
    """Map legacy->users (map statique : la table legacy n'existe plus)."""
    return dict(USER_FIELD_MAP)


def _dynamic_field_values(rec: MemberRecord) -> Dict[str, Optional[str]]:
    """Résout sur l'enregistrement les champs à longs libellés (photo / questionnaire de santé),
    dont la clé exacte dépend du formulaire HelloAsso."""
    out = {}
    try:
        rec_keys = list(rec.keys())
    except Exception:
        rec_keys = []
    for prefix, dst in DYNAMIC_USER_FIELDS:
        for k in rec_keys:
            if k.startswith(prefix):
                out[dst] = clean_legacy_text(_get(rec, k))
                break
    return out


def ensure_v2_schema(cur: sqlite3.Cursor) -> None:
    """Crée les tables v2 si absentes (idempotent)."""
    cur.executescript(V2_DDL)
    rename_gender_column(cur)


def rename_gender_column(cur: sqlite3.Cursor) -> None:
    """Existing databases: users.gender (free text) becomes users.sex (FFME code, plans/sex-enum.md).

    A Firestore cache is only renamed (its older CACHE_FORMAT has it rebuilt from Firestore; converting the
    values here would fire the tracking triggers and push them); a plain database gets its values converted."""
    columns = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "gender" not in columns or "sex" in columns:
        return
    cur.execute("ALTER TABLE users RENAME COLUMN gender TO sex")
    if cur.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_fs_changes'").fetchone():
        return
    for user_id, raw in cur.execute("SELECT id, sex FROM users WHERE sex IS NOT NULL").fetchall():
        sex = parse_sex(raw)
        cur.execute("UPDATE users SET sex = ? WHERE id = ?", (sex.value if sex else None, user_id))


def _inserted_id(cur: sqlite3.Cursor) -> int:
    """Id of the row the cursor just inserted (always set after a successful INSERT)."""
    if cur.lastrowid is None:
        raise sqlite3.DatabaseError("INSERT did not return a row id")
    return cur.lastrowid


def resolve_season_id(cur: sqlite3.Cursor, season_name: str) -> int:
    """Id of the season, created (inactive) when missing."""
    cur.execute("SELECT id FROM seasons WHERE name=?", (season_name,))
    row = cur.fetchone()
    if row:
        return int(row["id"] if isinstance(row, sqlite3.Row) else row[0])
    cur.execute("INSERT INTO seasons (name, is_active) VALUES (?, 0)", (season_name,))
    return _inserted_id(cur)


def add_missing_emergency_contacts(cur: sqlite3.Cursor, user_id: int, rec: MemberRecord, now_iso: str) -> None:
    """Adds the contacts of a record the member does not have yet, after theirs: rows already there are never changed
    (plans/emergency-contacts.md, D2). `rec` holds the two contacts of a form, or a list under `emergency_contacts`."""
    incoming = list(_get(rec, "emergency_contacts") or [])
    incoming += [{"name": _get(rec, name_key), "phone": _get(rec, phone_key)} for name_key, phone_key in HELLOASSO_CONTACT_FIELDS]
    rows = cur.execute("SELECT name, phone, position FROM emergency_contacts WHERE user_id = ?", (user_id,)).fetchall()
    next_position = max((row[2] for row in rows), default=-1) + 1
    existing = [EmergencyContact(row[0] or "", row[1] or "") for row in rows]
    for offset, contact in enumerate(missing_contacts(existing, incoming)):
        cur.execute("INSERT INTO emergency_contacts (user_id, name, phone, position, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, contact.name, contact.phone, next_position + offset, now_iso, now_iso))


def fill_blank_user_fields(cur: sqlite3.Cursor, user_id: int, rec: MemberRecord, now_iso: str,
                           field_map: Mapping[str, str]) -> None:
    """Copies the fields of `rec` into the user's columns that are still blank: a value of the base is never overwritten.
    The contacts of `rec` the member does not have yet are added."""
    add_missing_emergency_contacts(cur, user_id, rec, now_iso)
    dyn = _dynamic_field_values(rec)
    for src_col, dst_col in field_map.items():
        new_val = clean_legacy_text(_get(rec, src_col))
        if new_val:
            if dst_col == "sex":
                new_val = sex_code(new_val, _get(rec, "order_ref"))
                if new_val is None:
                    continue
            cur.execute(
                f'UPDATE users SET "{dst_col}" = ?, updated_at = ? '  # noqa: S608 - dst_col issu de USER_FIELD_MAP
                f'WHERE id = ? AND (("{dst_col}" IS NULL) OR (TRIM("{dst_col}") = ""))',
                (new_val, now_iso, user_id),
            )
    for dst_col, new_val in dyn.items():
        if new_val:
            cur.execute(
                f'UPDATE users SET "{dst_col}" = ?, updated_at = ? '  # noqa: S608 - dst_col issu de DYNAMIC_USER_FIELDS
                f'WHERE id = ? AND (("{dst_col}" IS NULL) OR (TRIM("{dst_col}") = ""))',
                (new_val, now_iso, user_id),
            )


def upsert_user_v2(cur: sqlite3.Cursor, rec: MemberRecord, now_iso: str,
                   field_map: Mapping[str, str]) -> Tuple[int, bool]:
    """Crée ou complète un user. rec = dict HelloAsso ou ligne legacy (adherents JOIN seasons).
    Retourne (user_id, created)."""
    last = str(_get(rec, "user_lastName") or "").strip()
    first = str(_get(rec, "user_firstName") or "").strip()
    dob_raw = str(_get(rec, DOB_COLUMN) or "").strip()
    dob_iso = legacy_date_to_iso(dob_raw)
    k_last = normalize_name(last).upper()
    k_first = normalize_name(first).lower()

    cur.execute(
        "SELECT id FROM users WHERE last_name_key=? AND first_name_key=? AND birth_date=?",
        (k_last, k_first, dob_iso),
    )
    found = cur.fetchone()
    if found:
        user_id = found["id"] if isinstance(found, sqlite3.Row) else found[0]
        # Rattacher l'identifiant legacy si connu (fusion utilisateur migrée + sync)
        legacy_id = _get(rec, "adherent_id")
        if legacy_id is not None:
            cur.execute("UPDATE users SET legacy_adherent_id=? WHERE id=? AND legacy_adherent_id IS NULL",
                        (legacy_id, user_id))
        fill_blank_user_fields(cur, user_id, rec, now_iso, field_map)
        return user_id, False

    values = {dst: clean_legacy_text(_get(rec, src)) for src, dst in field_map.items()}
    if "sex" in values:
        values["sex"] = sex_code(values["sex"], _get(rec, "order_ref"))
    values["last_name"] = last
    values["first_name"] = first
    values["last_name_key"] = k_last
    values["first_name_key"] = k_first
    values["birth_date"] = dob_iso
    values["birth_date_raw"] = dob_raw if dob_raw else None
    values.update(_dynamic_field_values(rec))
    legacy_id = _get(rec, "adherent_id")
    if legacy_id is not None:
        values["legacy_adherent_id"] = legacy_id
    cols = list(values.keys())
    try:
        cur.execute(
            f'INSERT INTO users ({", ".join(chr(34) + c + chr(34) for c in cols)}) '  # noqa: S608 - colonnes issues de USER_FIELD_MAP, DYNAMIC_USER_FIELDS et de littéraux
            f'VALUES ({", ".join("?" for _ in cols)})',
            [values[c] for c in cols],
        )
        user_id = _inserted_id(cur)
    except sqlite3.IntegrityError:
        cur.execute(
            "SELECT id FROM users WHERE last_name_key=? AND first_name_key=? AND birth_date=?",
            (k_last, k_first, dob_iso),
        )
        row = cur.fetchone()
        user_id = row["id"] if isinstance(row, sqlite3.Row) else row[0]
        return user_id, False
    cur.execute("UPDATE users SET created_at=?, updated_at=? WHERE id=?", (now_iso, now_iso, user_id))
    add_missing_emergency_contacts(cur, user_id, rec, now_iso)
    return user_id, True


def upsert_order_v2(cur: sqlite3.Cursor, order_ref: str, order_date: object, status: object,
                    payer_last: object = "", payer_first: object = "", payer_email: object = "",
                    season_id: Optional[int] = None, now_iso: Optional[str] = None) -> Optional[int]:
    """Crée ou met à jour la commande (statut le plus actif conservé, payeur complété)."""
    cur.execute("SELECT id, status, payer_last_name, payer_first_name, payer_email, season_id "
                "FROM orders WHERE order_ref=?", (order_ref,))
    found = cur.fetchone()
    if found:
        order_id = found["id"] if isinstance(found, sqlite3.Row) else found[0]
        ex_status = found["status"] if isinstance(found, sqlite3.Row) else found[1]
        if status_score(status) > status_score(ex_status):
            cur.execute("UPDATE orders SET status=?, status_normalized=?, updated_at=? WHERE id=?",
                        (status, normalize_status(status), now_iso, order_id))
        cols = (("payer_last_name", payer_last), ("payer_first_name", payer_first), ("payer_email", payer_email))
        for i, (col, val) in enumerate(cols):
            v = str(val or "").strip()
            existing = found[col] if isinstance(found, sqlite3.Row) else found[2 + i]
            if v and not str(existing or "").strip():
                cur.execute(f"UPDATE orders SET {col}=?, updated_at=? WHERE id=?", (v, now_iso, order_id))  # noqa: S608 - noms de colonnes littéraux du code
        if season_id and not (found["season_id"] if isinstance(found, sqlite3.Row) else found[5]):
            cur.execute("UPDATE orders SET season_id=? WHERE id=?", (season_id, order_id))
        return order_id

    cur.execute("""
        INSERT INTO orders (order_ref, order_date, status, status_normalized,
                            payer_last_name, payer_first_name, payer_email,
                            season_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_ref, str(order_date or ""), str(status or ""), normalize_status(status),
          str(payer_last or "").strip(), str(payer_first or "").strip(), str(payer_email or "").strip(),
          season_id, now_iso, now_iso))
    return cur.lastrowid


def _season_sibling_scores(cur: sqlite3.Cursor, user_id: Optional[int], order_id: Optional[int]) -> list[tuple[int, int]]:
    """(purchase_id, score de priorité) des autres purchases du même user dans la même saison.
    Lecture par index : valable pour un sqlite3.Row comme pour un tuple."""
    cur.execute("""
        SELECT p.id, p.status, p.tarif_name, p.amount
        FROM purchases p JOIN orders o ON o.id = p.order_id
        WHERE p.user_id = ? AND o.season_id = (SELECT season_id FROM orders WHERE id = ?)
          AND p.id != ?
    """, (user_id, order_id, order_id))
    return [(row[0], purchase_priority_score(row[1], row[2], row[3])) for row in cur.fetchall()]


def _has_better_sibling_purchase(cur: sqlite3.Cursor, user_id: Optional[int], order_id: Optional[int], score: int) -> bool:
    """Vrai si une autre purchase du même user dans la même saison a un score de statut
    strictement supérieur. Reproduit la sémantique legacy : une inscription moins
    prioritaire (annulée / liste d'attente) ne doit jamais masquer une inscription active."""
    return any(sibling_score > score for _, sibling_score in _season_sibling_scores(cur, user_id, order_id))


def insert_purchase_v2(cur: sqlite3.Cursor, order_id: Optional[int], user_id: Optional[int], rec: MemberRecord,
                       now_iso: str, legacy_adherent_id: Optional[int] = None,
                       legacy_season_id: Optional[int] = None) -> Optional[int]:
    """Insère ou met à jour l'achat avec la règle de priorité de statut centralisée.
    Retourne purchase_id, ou None si une inscription plus prioritaire existe déjà."""
    try:
        amt_val = float(_get(rec, "amount") or 0.0)
    except (ValueError, TypeError):
        amt_val = 0.0
    new_status = str(_get(rec, "status") or "Validé").strip()
    # Normalisation : supprimer les espaces de début/fin (sinon des variantes
    # comme "Liste d'attente cours " et "Liste d'attente cours" coexistent en BDD)
    tarif = str(_get(rec, "tarif_name") or "").strip()
    new_score = purchase_priority_score(new_status, tarif, amt_val)

    cur.execute("SELECT id, status, tarif_name, amount FROM purchases WHERE order_id=? AND user_id=?",
                (order_id, user_id))
    found = cur.fetchone()
    if found:
        purchase_id = found[0]  # index: valable pour un sqlite3.Row comme pour un tuple
        if purchase_priority_score(found[1], found[2], found[3]) > new_score:
            return None
        if _has_better_sibling_purchase(cur, user_id, order_id, new_score):
            return None
        cur.execute("""
            UPDATE purchases SET tarif_name=?, amount=?, status=?, status_normalized=?,
                                 is_modified=?, commentaires_correctif=?, email_sent_date=?, updated_at=?
            WHERE id=?
        """, (tarif, amt_val, new_status, normalize_status(new_status),
              _get(rec, "is_modified") or "Non", clean_legacy_text(_get(rec, "commentaires_correctif")) or "",
              _get(rec, "email_sent_date"), now_iso, purchase_id))
        return purchase_id

    if _has_better_sibling_purchase(cur, user_id, order_id, new_score):
        return None

    # Sémantique legacy d'écrasement : la nouvelle inscription plus prioritaire remplace
    # les inscriptions STRICTEMENT moins prioritaires du même user dans la même saison.
    for sibling_id, sibling_score in _season_sibling_scores(cur, user_id, order_id):
        if sibling_score < new_score:
            cur.execute("DELETE FROM purchase_options WHERE purchase_id=?", (sibling_id,))
            cur.execute("DELETE FROM purchases WHERE id=?", (sibling_id,))

    cur.execute("""
        INSERT INTO purchases (order_id, user_id, tarif_name, amount, status, status_normalized,
                               is_tribe, email_sent_date, is_modified, commentaires_correctif,
                               legacy_adherent_id, legacy_season_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, user_id, tarif, amt_val, new_status, normalize_status(new_status),
          "Oui" if is_true(_get(rec, "champ_Famille : nous sommes une tribu de 3 ou plus inscrits ce qui permet un code de réduction : FAMILLE")) else "Non",
          _get(rec, "email_sent_date"),
          _get(rec, "is_modified") or "Non",
          clean_legacy_text(_get(rec, "commentaires_correctif")) or "",
          legacy_adherent_id, legacy_season_id, now_iso, now_iso))
    purchase_id = cur.lastrowid
    _write_ffme_category(cur, user_id, order_id, now_iso)
    return purchase_id


def _write_ffme_category(cur: sqlite3.Cursor, user_id: Optional[int], order_id: Optional[int], now_iso: str) -> None:
    """A new membership (import, renewal, manual addition): the member's FFME category for the order's season, over
    any earlier value (plans/ffme-categories.md D4). Updates of an existing membership never come here."""
    row = cur.execute("SELECT u.birth_date, s.name FROM users u, orders o JOIN seasons s ON s.id = o.season_id"
                      " WHERE u.id = ? AND o.id = ?", (user_id, order_id)).fetchone()
    if row is None:
        return
    category = category_for(parse_birth_date(row[0]), row[1])
    cur.execute("UPDATE users SET ffme_category = ?, updated_at = ? WHERE id = ?", (category or "", now_iso, user_id))


def insert_options_v2(cur: sqlite3.Cursor, purchase_id: Optional[int], rec: MemberRecord) -> int:
    """Insère les options d'assurance souscrites (1 ligne par option). Retourne le nombre ajouté."""
    added = 0
    for opt_name, col_has, col_amount in OPTION_PAIRS:
        if is_true(_get(rec, col_has)):
            try:
                amt = float(_get(rec, col_amount) or 0.0)
            except (ValueError, TypeError):
                amt = 0.0
            try:
                cur.execute("INSERT INTO purchase_options (purchase_id, option_name, amount) VALUES (?, ?, ?)",
                            (purchase_id, opt_name, amt))
                added += 1
            except sqlite3.IntegrityError:
                pass
    return added


def write_members_to_v2(cur: sqlite3.Cursor, members: Iterable[MemberRecord], season_name: str) -> Dict[str, int]:
    """Écrit un lot d'adhésions dans le schéma v2, payeurs (payer_*) compris.
    Appelé par MemberRepository.upsert_members (même transaction)."""
    ensure_v2_schema(cur)
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    season_id = resolve_season_id(cur, season_name)
    field_map = build_user_field_map(cur)

    stats = {"users": 0, "orders": 0, "purchases": 0, "options": 0, "skipped_priority": 0}
    for m in members:
        order_ref = str(_get(m, "order_ref") or "").strip()
        if not order_ref:
            continue
        user_id, _created = upsert_user_v2(cur, m, now_iso, field_map)
        stats["users"] += 1
        order_id = upsert_order_v2(
            cur, order_ref, _get(m, "order_date"), _get(m, "status"),
            _get(m, "payer_lastName"), _get(m, "payer_firstName"), _get(m, "payer_email"),
            season_id, now_iso,
        )
        stats["orders"] += 1
        purchase_id = insert_purchase_v2(cur, order_id, user_id, m, now_iso, legacy_season_id=season_id)
        if purchase_id is None:
            stats["skipped_priority"] += 1
            continue
        stats["purchases"] += 1
        stats["options"] += insert_options_v2(cur, purchase_id, m)
    return stats




# Flat member view: one row per purchase (users ⨝ orders ⨝ purchases ⨝ seasons), with the insurance options as
# opt_* columns. Read by the FFME export, the attendance sheets, the reports and the competitions' member directory.
# The insurance options are read at user level (any purchase of the member carrying them).
def _option_columns() -> str:
    """Two columns of the flat view per insurance option: « Oui » when the member's purchase has it, and its amount."""
    columns = []
    for option, has_column, amount_column in OPTION_PAIRS:
        for value, column in (("CASE WHEN po2.id IS NOT NULL THEN 'Oui' END", has_column), ("po2.amount", amount_column)):
            columns.append(f"""    (SELECT {value}
       FROM purchase_options po2 JOIN purchases p2 ON p2.id = po2.purchase_id
      WHERE p2.user_id = u.id AND po2.option_name = '{option.replace("'", "''")}' LIMIT 1) AS "{column}",""")  # noqa: S608 - option and column names from INSURANCE_OPTIONS
    return "\n".join(columns)


# Option names and column names come from INSURANCE_OPTIONS (code constants), never from data
MEMBER_FLAT_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_member_flat AS
SELECT
    u.id AS "user_id",
    u.last_name AS "last_name",
    u.first_name AS "first_name",
    u.birth_date AS "birth_date",
    u.birth_date_raw AS "birth_date_raw",
    u.sex AS "sex",
    u.nationality AS "nationality",
    u.address AS "address",
    u.zip_code AS "zip_code",
    u.city AS "city",
    u.country AS "country",
    u.phone AS "phone",
    u.email_primary AS "email_primary",
    u.email_secondary AS "email_secondary",
    COALESCE((SELECT ec.name FROM emergency_contacts ec WHERE ec.user_id = u.id ORDER BY ec.position, ec.id LIMIT 1), '') AS "emergency1_name",
    COALESCE((SELECT ec.phone FROM emergency_contacts ec WHERE ec.user_id = u.id ORDER BY ec.position, ec.id LIMIT 1), '') AS "emergency1_phone",
    p.is_tribe AS "is_tribe",
    u.licence_ffme AS "licence_ffme",
    u.ffme_category AS "ffme_category",
    u.photo_auth AS "photo_auth",
    u.health_commitment AS "health_commitment",
{option_columns}
    u.badge_rouge AS "badge_rouge",
    u.autonomie_bloc AS "autonomie_bloc",
    u.raw_passports AS "raw_passports",
    u.raw_diplomas AS "raw_diplomas",
    u.parental_auth_autonomous AS "parental_auth_autonomous",
    u.parental_auth_family AS "parental_auth_family",
    o.payer_last_name AS "payer_last_name",
    o.payer_first_name AS "payer_first_name",
    o.payer_email AS "payer_email",
    o.payment_method AS "payment_method",
    o.promo_code AS "promo_code",
    o.order_ref AS "order_ref",
    o.order_date AS "order_date",
    p.tarif_name AS "tarif_name",
    p.amount AS "amount",
    p.status AS "status",
    p.is_modified AS "is_modified",
    p.commentaires_correctif AS "commentaires_correctif",
    p.email_sent_date AS "email_sent_date",
    p.document_sante AS "document_sante",
    s.name AS "season_name",
    (SELECT COUNT(*) FROM purchases p3
      WHERE p3.user_id = u.id AND p3.legacy_season_id != p.legacy_season_id) AS "already_member"
FROM purchases p
JOIN users u ON u.id = p.user_id
JOIN orders o ON o.id = p.order_id
JOIN seasons s ON s.id = o.season_id
""".replace("{option_columns}", _option_columns())


# The key on the member record, replaced by Outils › Clés (plans/club-keys.md): dropped from existing caches
FORMER_USER_COLUMNS = ("hid_proxkey", "hid_proxkey_date", "hid_proxkey_comment")


def drop_former_user_columns(cur: sqlite3.Cursor) -> None:
    """Drops the users columns no longer used. DDL fires no tracking trigger: nothing is sent to Firestore, whose
    documents keep the fields (the cache only reads its own columns). The member views reading them are dropped
    first; recreate_member_flat_view() creates the current one again."""
    columns = {r[1] for r in cur.execute("PRAGMA table_info(users)")}
    former = [c for c in FORMER_USER_COLUMNS if c in columns]
    if not former:
        return
    cur.execute("DROP VIEW IF EXISTS v_adherents_legacy")
    cur.execute("DROP VIEW IF EXISTS v_member_flat")
    for column in former:
        logger.info(f"[SQLITE] Suppression de la colonne users.{column} (clés : Outils › Clés)")
        cur.execute(f"ALTER TABLE users DROP COLUMN {column}")  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query - column names from FORMER_USER_COLUMNS


def recreate_member_flat_view(cur: sqlite3.Cursor) -> None:
    """Creates the flat member view again with the current definition (CREATE VIEW IF NOT EXISTS does not update an
    existing one)."""
    cur.execute("DROP VIEW IF EXISTS v_adherents_legacy")  # its former name, in existing cache files
    cur.execute("DROP VIEW IF EXISTS v_member_flat")
    cur.execute(MEMBER_FLAT_VIEW_SQL)
