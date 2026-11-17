"""Members (schema v2: users / orders / purchases / purchase_options): reads, imports, edits."""

from __future__ import annotations

import datetime
import logging
import sqlite3
from typing import Any, Dict, Iterable, List, Mapping, Optional

from domain.errors import InvalidRequest
from domain.members.emergency_contacts import EmergencyContact, clean_contacts, keep_stored_values
from domain.members.sex import parse_sex
from domain.utils import normalize_name
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase

logger = logging.getLogger("alj")

HIGHER_PRIORITY_REGISTRATION = ("Une inscription plus prioritaire existe déjà pour cet adhérent "
                                "cette saison (statut/montant supérieurs).")
DUPLICATE_MEMBER = "Un autre adhérent avec les mêmes nom, prénom et date de naissance existe déjà."

EXTRA_COLUMNS = {
    "is_modified": "TEXT DEFAULT 'Non'",
    "commentaires_correctif": "TEXT DEFAULT ''",
    "badge_rouge": "TEXT DEFAULT 'Non'",
    "autonomie_bloc": "TEXT DEFAULT 'Non'",
    "raw_passports": "TEXT DEFAULT ''",
    "raw_diplomas": "TEXT DEFAULT ''",
    "parental_auth_autonomous": "TEXT DEFAULT 'Non'",
    "parental_auth_family": "TEXT DEFAULT 'Non'",
}


# A row of a member read: column -> value. Any: SQLite values (text, number or None) of many columns
MemberRow = Dict[str, Any]
# A flat member record to write (HelloAsso export keys, or the fields of a manual addition). Any: as above
MemberRecord = Mapping[str, Any]


def replace_emergency_contacts(cur: sqlite3.Cursor, user_id: int, contacts: Iterable[Mapping[str, object]], now_iso: str) -> None:
    """Makes the member's contacts exactly `contacts`, in that order: rows are reused by position, and those that do
    not change are not rewritten, so the sync only sends what changed. A contact sent as the form shows it keeps its stored values."""
    rows = cur.execute("SELECT id, name, phone, position FROM emergency_contacts WHERE user_id = ? ORDER BY position, id", (user_id,)).fetchall()
    wanted = keep_stored_values(clean_contacts(contacts), [EmergencyContact(row[1] or "", row[2] or "") for row in rows])
    for position, contact in enumerate(wanted):
        if position >= len(rows):
            cur.execute("INSERT INTO emergency_contacts (user_id, name, phone, position, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_id, contact.name, contact.phone, position, now_iso, now_iso))
        elif tuple(rows[position])[1:] != (contact.name, contact.phone, position):
            cur.execute("UPDATE emergency_contacts SET name = ?, phone = ?, position = ?, updated_at = ? WHERE id = ?",
                        (contact.name, contact.phone, position, now_iso, rows[position][0]))
    for surplus in rows[len(wanted):]:
        cur.execute("DELETE FROM emergency_contacts WHERE id = ?", (surplus[0],))


class MemberRepository:
    @classmethod
    def list_flat_member_rows(cls, season: Optional[str]) -> List[MemberRow]:
        """Purchases of `season` (None: every season) from the flat member view, newest members first. Callers that
        need an order of their own sort the rows themselves (the FFME export, the attendance sheets)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            if season is None:
                rows = conn.execute('SELECT * FROM v_member_flat ORDER BY "user_id" DESC').fetchall()
            else:
                rows = conn.execute('SELECT * FROM v_member_flat WHERE season_name = ? ORDER BY "user_id" DESC',
                                    (season,)).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]


    # One row per purchase (users ⨝ orders ⨝ purchases ⨝ seasons), the fields of the web member pages
    _MEMBER_ROWS_SELECT = """
        SELECT u.id AS user_id, p.id AS purchase_id,
               u.last_name, u.first_name, u.birth_date, u.sex,
               u.address, u.zip_code, u.city, u.country, u.nationality, u.phone, u.email_primary, u.email_secondary,
               u.licence_ffme, u.health_commitment, u.photo_auth, u.badge_rouge, u.autonomie_bloc,
               u.raw_passports, u.raw_diplomas,
               o.payer_first_name, o.payer_last_name, o.payer_email, o.order_ref, o.order_date,
               p.tarif_name, p.amount, p.status, p.document_sante, p.email_sent_date,
               p.commentaires_correctif,
               s.name AS season_name
    """
    _MEMBER_ROWS_FROM = """
        FROM purchases p
        JOIN users u ON u.id = p.user_id
        JOIN orders o ON o.id = p.order_id
        JOIN seasons s ON s.id = o.season_id
    """

    @classmethod
    def _query_member_rows(cls, where: str, params: tuple) -> List[MemberRow]:
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            rows = [dict(r) for r in conn.execute(f"{cls._MEMBER_ROWS_SELECT} {cls._MEMBER_ROWS_FROM} WHERE {where}", params).fetchall()]
            contacts_by_user: Dict[int, List[Dict[str, str]]] = {}
            for contact in conn.execute(
                    f"SELECT user_id, name, phone FROM emergency_contacts WHERE user_id IN (SELECT p.user_id {cls._MEMBER_ROWS_FROM} WHERE {where}) "  # noqa: S608 - fragments SQL littéraux du code, valeurs en paramètres
                    "ORDER BY user_id, position, id", params).fetchall():
                contacts_by_user.setdefault(contact["user_id"], []).append({"name": contact["name"] or "", "phone": contact["phone"] or ""})
            for row in rows:
                row["emergency_contacts"] = contacts_by_user.get(row["user_id"], [])
            return rows
        finally:
            conn.close()

    @classmethod
    def list_member_rows(cls, season_name: str) -> List[MemberRow]:
        """One row per purchase of the season (users ⨝ orders ⨝ purchases), with the fields of
        the web member pages. Unlike the flat member view, carries `purchase_id` (needed by
        /api/members/update) and skips the insurance-option subqueries."""
        return cls._query_member_rows("s.name = ?", (season_name,))

    @classmethod
    def list_member_rows_of_users(cls, user_ids: Iterable[int]) -> List[MemberRow]:
        """Rows of list_member_rows for these users only, every season."""
        ids = tuple(user_ids)
        if not ids:
            return []
        return cls._query_member_rows(f"u.id IN ({', '.join('?' * len(ids))})", ids)

    @classmethod
    def upsert_members(cls, members: List[MemberRecord], season_name: str) -> int:
        """Insère ou met à jour un lot d'adhérents dans le schéma v2 (users / orders / purchases / purchase_options).
        Returns the number of purchases written; a database failure is rolled back and raised."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cursor = conn.cursor()
            stats = schema_v2.write_members_to_v2(cursor, members, season_name)
            inserted_count = stats["purchases"]
            conn.commit()
            logger.info(f"[SQLITE] Synchro reussie : {inserted_count} adhesions enregistrees/mises a jour "
                  f"pour la saison {season_name}. (v2: {stats})")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return inserted_count


    @classmethod
    def add_manual_member(cls, fields: dict, season_name: str) -> str:
        """
        Ajoute manuellement un adhérent dans le schéma v2 (users + orders + purchases),
        en synthétisant une commande « MANUEL-... » équivalente à une inscription HelloAsso.
        Champs attendus : last_name, first_name, birth_date ('JJ/MM/AAAA' ou ISO), sex,
        phone, email_primary, address, zip_code, city, country, nationality, tarif_name, status, amount.
        Returns the order reference. InvalidRequest when a registration with a higher priority already exists;
        a database error is rolled back and raised.
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            now = datetime.datetime.now()
            order_ref = f"MANUEL-{now.strftime('%Y%m%d-%H%M%S')}"
            payer_email = str(fields.get("email_primary") or "").strip()

            rec = {
                "order_ref": order_ref,
                "order_date": now.strftime("%Y-%m-%d"),
                "status": str(fields.get("status") or "Validé").strip(),
                "tarif_name": str(fields.get("tarif_name") or "").strip(),
                "amount": float(fields.get("amount") or 0.0),
                "user_lastName": str(fields.get("last_name") or "").strip(),
                "user_firstName": str(fields.get("first_name") or "").strip(),
                schema_v2.DOB_COLUMN: str(fields.get("birth_date") or "").strip(),
                "champ_Sexe": str(fields.get("sex") or "").strip(),
                "champ_Téléphone ": str(fields.get("phone") or "").strip(),
                "champ_Adresse mail pour la réception des informations du club": payer_email,
                "champ_Adresse : numéro et nom de rue": str(fields.get("address") or "").strip(),
                "champ_Code postal": str(fields.get("zip_code") or "").strip(),
                "champ_Ville": str(fields.get("city") or "").strip(),
                "champ_Pays": str(fields.get("country") or "France").strip(),
                "champ_Nationalité": str(fields.get("nationality") or "").strip(),
                "payer_lastName": str(fields.get("payer_lastName") or fields.get("payer_last_name") or fields.get("last_name") or "").strip(),
                "payer_firstName": str(fields.get("payer_firstName") or fields.get("payer_first_name") or fields.get("first_name") or "").strip(),
                "payer_email": str(fields.get("payer_email") or payer_email).strip(),
                "is_modified": "Non",
            }

            if "email_secondary" in fields:
                rec["champ_Deuxième adresse mail pour la réception des informations du club"] = str(fields.get("email_secondary") or "").strip()
            if "licence_ffme" in fields:
                rec["champ_Numéro de Licence FFME (6 chiffres)"] = str(fields.get("licence_ffme") or "").strip()
            if "badge_rouge" in fields:
                rec["badge_rouge"] = str(fields.get("badge_rouge") or "Non").strip()
            if "autonomie_bloc" in fields:
                rec["autonomie_bloc"] = str(fields.get("autonomie_bloc") or "Non").strip()
            if "emergency_contacts" in fields:
                rec["emergency_contacts"] = fields["emergency_contacts"] or []
            if "photo_auth" in fields:
                rec["champ_Autorisation d'utilisation de l'image (photos, vidéos)"] = str(fields.get("photo_auth") or "Oui").strip()
            comment = fields.get("commentaires_correctif") if "commentaires_correctif" in fields else fields.get("commentaire")
            if comment is not None:
                rec["commentaires_correctif"] = str(comment).strip()

            cursor = conn.cursor()
            stats = schema_v2.write_members_to_v2(cursor, [rec], season_name)
            if not stats.get("purchases"):
                conn.rollback()
                raise InvalidRequest(HIGHER_PRIORITY_REGISTRATION)
            conn.commit()
            # Personal data (names) never goes to the logs: the order reference identifies the purchase
            logger.info(f"[SQLITE] Manual member added ({order_ref}, season {season_name}).")
            return order_ref
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def list_contact_emails(cls) -> set[str]:
        """Every member and payer address in the database (lower-cased)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            emails: set[str] = set()
            for sql in ("SELECT email_primary, email_secondary FROM users", "SELECT payer_email FROM orders"):
                for row in conn.execute(sql).fetchall():
                    emails.update(str(v).strip().lower() for v in tuple(row) if v)
            emails.discard("")
            return emails
        finally:
            conn.close()

    @classmethod
    def get_users_by_ids(cls, ids: List[int]) -> Dict[int, dict]:
        """Contact details of the given users, keyed by id (unknown ids are omitted)."""
        ids = list(dict.fromkeys(ids or []))
        if not ids:
            return {}
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                "SELECT id, first_name, last_name, email_primary, email_secondary, phone, licence_ffme "  # noqa: S608 - uniquement des marqueurs ?
                f"FROM users WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            return {row["id"]: dict(row) for row in rows}
        finally:
            conn.close()


    @classmethod
    def update_email_sent_date(cls, order_ref: str, last_name: str, first_name: str, date_str: str, purchase_id: Optional[int] = None) -> bool:
        """Met à jour la date d'envoi d'e-mail sur les achats v2 de la commande.
        False when no purchase matches; a database failure is rolled back and raised."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            if purchase_id:
                cursor.execute("""
                    UPDATE purchases
                    SET email_sent_date = ?
                    WHERE id = ?
                """, (date_str, int(purchase_id)))
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.debug(f"[SQLITE] Date d'envoi d'e-mail enregistree pour l'achat #{purchase_id} : {date_str}")
                    return True

            cursor.execute("""
                UPDATE purchases
                SET email_sent_date = ?
                WHERE order_id IN (SELECT id FROM orders WHERE order_ref = ?)
                  AND user_id IN (
                      SELECT id FROM users
                      WHERE UPPER(TRIM(last_name)) = ? AND LOWER(TRIM(first_name)) = ?
                  )
            """, (date_str, str(order_ref or "").strip(),
                  str(last_name or "").strip().upper(), str(first_name or "").strip().lower()))
            rows_affected = cursor.rowcount
            if rows_affected == 0 and order_ref:
                cursor.execute("""
                    UPDATE purchases
                    SET email_sent_date = ?
                    WHERE order_id IN (SELECT id FROM orders WHERE order_ref = ?)
                """, (date_str, str(order_ref).strip()))
                rows_affected = cursor.rowcount
            conn.commit()
            if rows_affected > 0:
                logger.debug(f"[SQLITE] Date d'envoi d'e-mail enregistree pour la commande {order_ref} : {date_str}")
                return True
            logger.info(f"[SQLITE] Aucun achat trouve pour la commande {order_ref} (achat #{purchase_id})")
            return False
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def update_member_fields(
        cls,
        user_id: Optional[int] = None,
        fields: Optional[dict] = None,
        purchase_id: Optional[int] = None,
        order_ref: Optional[str] = None
    ) -> None:
        """
        Met à jour de manière ciblée les informations d'un adhérent :
        - Table users : badge_rouge, autonomie_bloc, email_primary, email_secondary, phone, sex…
        - Table purchases : tarif_name.
        InvalidRequest when nothing is given or when the change would duplicate another member; any other
        database error is rolled back and raised.
        """
        if not fields:
            raise InvalidRequest("Aucun champ à mettre à jour.")

        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            now_iso = datetime.datetime.now().isoformat(timespec="seconds")

            # Résolution de user_id si absent
            resolved_uid = user_id
            if resolved_uid is None and purchase_id:
                row = cursor.execute("SELECT user_id FROM purchases WHERE id = ?", (int(purchase_id),)).fetchone()
                if row:
                    resolved_uid = row["user_id"]

            if resolved_uid is None and order_ref:
                row = cursor.execute("""
                    SELECT p.user_id FROM purchases p
                    JOIN orders o ON o.id = p.order_id
                    WHERE o.order_ref = ?
                    LIMIT 1
                """, (str(order_ref).strip(),)).fetchone()
                if row:
                    resolved_uid = row["user_id"]

            user_updates = _user_column_updates(fields)
            if user_updates and resolved_uid is not None:
                sets = [f'"{col}" = ?' for col in user_updates.keys()]
                sets.append('updated_at = ?')
                params = list(user_updates.values()) + [now_iso, int(resolved_uid)]
                cursor.execute(f'UPDATE users SET {", ".join(sets)} WHERE id = ?', params)  # noqa: S608 - columns from _user_column_updates' fixed lists

            if fields.get("emergency_contacts") is not None and resolved_uid is not None:
                replace_emergency_contacts(cursor, int(resolved_uid), fields["emergency_contacts"], now_iso)

            purchase_updates = _purchase_column_updates(fields)
            if purchase_updates:
                _update_purchases(cursor, purchase_updates, purchase_id, order_ref, resolved_uid, now_iso)
            if "status" in purchase_updates:  # the order carries the status too
                status_params = (purchase_updates["status"], purchase_updates["status_normalized"], now_iso)
                if order_ref:
                    cursor.execute("""
                        UPDATE orders
                        SET status = ?, status_normalized = ?, updated_at = ?
                        WHERE order_ref = ?
                    """, (*status_params, str(order_ref).strip()))
                elif purchase_id:
                    cursor.execute("""
                        UPDATE orders
                        SET status = ?, status_normalized = ?, updated_at = ?
                        WHERE id = (SELECT order_id FROM purchases WHERE id = ?)
                    """, (*status_params, int(purchase_id)))

            conn.commit()
            logger.debug(f"[SQLITE] Adhérent #{resolved_uid} mis à jour avec succès : {list(fields.keys())}")
        except sqlite3.IntegrityError:
            conn.rollback()
            raise InvalidRequest(DUPLICATE_MEMBER) from None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# Member fields written as trimmed text, and the yes/no fields with their default
_USER_TEXT_FIELDS = (
    "email_primary", "email_secondary", "phone", "licence_ffme", "address", "zip_code", "city", "country", "nationality",
)
_USER_YES_NO_DEFAULTS = {"badge_rouge": "Non", "autonomie_bloc": "Non", "photo_auth": "Oui"}


def _user_column_updates(fields: Dict[str, object]) -> Dict[str, Optional[str]]:
    """users columns to write for the fields sent (an empty name is left unchanged)."""
    updates: Dict[str, Optional[str]] = {}
    last_name = str(fields.get("last_name") or "").strip().upper()
    if last_name:
        updates["last_name"] = last_name
        updates["last_name_key"] = normalize_name(last_name).upper()
    first_name = str(fields.get("first_name") or "").strip()
    if first_name:
        updates["first_name"] = first_name
        updates["first_name_key"] = normalize_name(first_name).lower()
    if "birth_date" in fields:
        raw_birth_date = str(fields["birth_date"] or "").strip()
        updates["birth_date"] = schema_v2.legacy_date_to_iso(raw_birth_date) if raw_birth_date else ""
        updates["birth_date_raw"] = raw_birth_date
    for column, default in _USER_YES_NO_DEFAULTS.items():
        if column in fields:
            updates[column] = str(fields[column] or default).strip()
    for column in _USER_TEXT_FIELDS:
        if column in fields:
            updates[column] = str(fields[column] or "").strip()
    if "sex" in fields:
        sex = parse_sex(fields["sex"])
        updates["sex"] = sex.value if sex else None
    return updates


def _normalized_status(status: str) -> str:
    lowered = status.lower()
    if lowered in ("processed", "validated", "validé", "valide"):
        return "Validé"
    if lowered in ("annulé", "annule", "canceled", "cancelled"):
        return "Annulé"
    return status.title()


def _purchase_column_updates(fields: Dict[str, object]) -> Dict[str, object]:
    """purchases columns to write for the fields sent (an empty tariff or status is left unchanged)."""
    updates: Dict[str, object] = {}
    tariff = str(fields.get("tarif_name") or "").strip()
    if tariff:
        updates["tarif_name"] = tariff
    if fields.get("amount") is not None:
        updates["amount"] = float(fields["amount"])  # type: ignore[arg-type]  # validated by MemberFields (a number)
    status = str(fields.get("status") or "").strip()
    if status:
        updates["status"] = status
        updates["status_normalized"] = _normalized_status(status)
    comment = next((fields[key] for key in ("commentaires_correctif", "commentaire", "comment") if key in fields), None)
    if comment is not None:
        updates["commentaires_correctif"] = str(comment or "").strip()
    return updates


def _update_purchases(cursor: sqlite3.Cursor, updates: Dict[str, object], purchase_id: Optional[int],
                      order_ref: Optional[str], user_id: Optional[int], now_iso: str) -> None:
    """Writes `updates` on the edited purchase: by id, else the member's purchase of the order, else all the member's
    purchases. Marks it as edited by hand (is_modified)."""
    sets = ", ".join(f'"{column}" = ?' for column in updates) + ", updated_at = ?, is_modified = 'Oui'"
    values = [*updates.values(), now_iso]
    if purchase_id:
        cursor.execute(f"UPDATE purchases SET {sets} WHERE id = ?", (*values, int(purchase_id)))  # noqa: S608 - columns from _purchase_column_updates
    elif order_ref and user_id:
        cursor.execute(f"UPDATE purchases SET {sets} WHERE user_id = ? AND order_id IN "  # noqa: S608 - as above
                       "(SELECT id FROM orders WHERE order_ref = ?)", (*values, int(user_id), str(order_ref).strip()))
    elif user_id:
        cursor.execute(f"UPDATE purchases SET {sets} WHERE user_id = ?", (*values, int(user_id)))  # noqa: S608 - as above
