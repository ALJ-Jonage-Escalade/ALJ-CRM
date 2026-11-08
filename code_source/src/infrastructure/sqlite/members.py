"""Members (schema v2: users / orders / purchases / purchase_options): reads, imports, edits."""

from __future__ import annotations

import datetime
import sqlite3
from typing import Dict, Iterable, List, Optional, Tuple


from domain.members.sex import parse_sex
from domain.utils import normalize_name
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import SqliteDatabase

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


class MemberRepository:
    @classmethod
    def load_direct_data(cls, season_filter: str = "2026-2027") -> list:
        """
        Charge les données d'adhérents depuis la vue de compatibilité (schéma v2)
        pour une saison spécifique ou un filtre comparatif.
        """
        # Résolution pour la rétrocompatibilité (si un chemin de fichier Excel .xlsx est passé)
        if isinstance(season_filter, str) and (season_filter.endswith(".xlsx") or "\\" in season_filter or "/" in season_filter):
            season_filter = "2026-2027" # Par défaut

        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            return cls._load_data_from_compat_view(conn, season_filter)
        finally:
            conn.close()

    @classmethod
    def _load_data_from_compat_view(cls, conn, season_filter: str) -> list:
        """Chargement via la vue v_adherents_legacy (schéma v2), aux clés plates historiques."""
        cursor = conn.cursor()
        if season_filter in ("Tous", "Toutes les saisons", "Toutes les saisons confondues"):
            cursor.execute('SELECT * FROM v_adherents_legacy ORDER BY "id" DESC')
        elif season_filter in ("Non réinscrits", "Anciens (25-26) non réinscrits en 26-27", "Anciens non réinscrits (Présents en 25/26 mais pas en 26/27)"):
            cursor.execute("""
                SELECT * FROM v_adherents_legacy
                WHERE season_name = '2025-2026'
                  AND "user_id" NOT IN (
                      SELECT "user_id" FROM v_adherents_legacy WHERE season_name = '2026-2027'
                  )
                ORDER BY "id" DESC
            """)
        else:
            cursor.execute('SELECT * FROM v_adherents_legacy WHERE season_name = ? ORDER BY "id" DESC', (season_filter,))

        rows = cursor.fetchall()
        participants_data = []
        for row in rows:
            row_dict = dict(row)
            # Supprimer le champ d'identifiant interne (comme le chemin legacy)
            row_dict.pop("id", None)
            participants_data.append(row_dict)
        return participants_data


    # One row per purchase (users ⨝ orders ⨝ purchases ⨝ seasons), the fields of the web member pages
    _MEMBER_ROWS_SQL = """
        SELECT u.id AS user_id, p.id AS purchase_id,
               u.last_name, u.first_name, u.birth_date, u.sex,
               u.address, u.zip_code, u.city, u.phone, u.email_primary, u.email_secondary,
               u.emergency1_name, u.emergency1_phone, u.emergency2_name, u.emergency2_phone,
               u.licence_ffme, u.health_commitment, u.photo_auth, u.badge_rouge, u.autonomie_bloc,
               u.hid_proxkey, u.hid_proxkey_date, u.hid_proxkey_comment,
               u.raw_passports, u.raw_diplomas,
               o.payer_first_name, o.payer_last_name, o.payer_email, o.order_ref, o.order_date,
               p.tarif_name, p.amount, p.status, p.document_sante, p.email_sent_date,
               p.commentaires_correctif,
               s.name AS season_name
        FROM purchases p
        JOIN users u ON u.id = p.user_id
        JOIN orders o ON o.id = p.order_id
        JOIN seasons s ON s.id = o.season_id
    """

    @classmethod
    def _query_member_rows(cls, where: str, params: tuple) -> list:
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            return [dict(r) for r in conn.execute(f"{cls._MEMBER_ROWS_SQL} WHERE {where}", params).fetchall()]
        finally:
            conn.close()

    @classmethod
    def list_member_rows(cls, season_name: str) -> list:
        """One row per purchase of the season (users ⨝ orders ⨝ purchases), with the fields of
        the web member pages. Unlike v_adherents_legacy, carries `purchase_id` (needed by
        /api/members/update) and skips the insurance-option subqueries."""
        return cls._query_member_rows("s.name = ?", (season_name,))

    @classmethod
    def list_member_rows_of_users(cls, user_ids: Iterable[int]) -> list:
        """Rows of list_member_rows for these users only, every season."""
        ids = tuple(user_ids)
        if not ids:
            return []
        return cls._query_member_rows(f"u.id IN ({', '.join('?' * len(ids))})", ids)

    @classmethod
    def upsert_members(cls, members: list, season_name: str = "2026-2027") -> int:
        """Insère ou met à jour un lot d'adhérents dans le schéma v2 (users / orders / purchases / purchase_options).
        Returns the number of purchases written; a database failure is rolled back and raised."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            cursor = conn.cursor()
            stats = schema_v2.sync_members_to_v2(cursor, members, season_name)
            inserted_count = stats["purchases"]
            conn.commit()
            print(f"[SQLITE] Synchro reussie : {inserted_count} adhesions enregistrees/mises a jour "
                  f"pour la saison {season_name}. (v2: {stats})")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return inserted_count


    @classmethod
    def add_manual_member(cls, fields: dict, season_name: str = "2026-2027") -> Tuple[bool, str]:
        """
        Ajoute manuellement un adhérent dans le schéma v2 (users + orders + purchases),
        en synthétisant une commande « MANUEL-... » équivalente à une inscription HelloAsso.
        Champs attendus : last_name, first_name, birth_date ('JJ/MM/AAAA' ou ISO), sex,
        phone, email_primary, address, zip_code, city, tarif_name, status, amount.
        Retourne (True, order_ref) ou (False, message) quand une inscription prioritaire existe déjà ;
        une erreur de base de données est annulée (rollback) et propagée.
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
                "champ_Pays": "France",
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
            if "emergency1_name" in fields:
                rec["champ_Personne à prévenir en cas d'urgence - NOM  et PRENOM en majuscule"] = str(fields.get("emergency1_name") or "").strip()
            if "emergency1_phone" in fields:
                rec["champ_Personne à prévenir en cas d'urgence - Téléphone"] = str(fields.get("emergency1_phone") or "").strip()
            if "emergency2_name" in fields:
                rec["champ_Parent 2  à prévenir en cas d'urgence - NOM ET PRENOM (en majuscule)"] = str(fields.get("emergency2_name") or "").strip()
            if "emergency2_phone" in fields:
                rec["champ_Parent 2 - Numéro de téléphone portable"] = str(fields.get("emergency2_phone") or "").strip()
            if "photo_auth" in fields:
                rec["champ_Autorisation d'utilisation de l'image (photos, vidéos)"] = str(fields.get("photo_auth") or "Oui").strip()
            if "hid_proxkey" in fields:
                val = fields.get("hid_proxkey")
                rec["hid_proxkey"] = "Oui" if (val is True or str(val or "").strip().lower() in ("oui", "true", "1", "yes")) else "Non"
            if "hid_proxkey_date" in fields:
                rec["hid_proxkey_date"] = str(fields.get("hid_proxkey_date") or "").strip()
            if "hid_proxkey_comment" in fields:
                rec["hid_proxkey_comment"] = str(fields.get("hid_proxkey_comment") or "").strip()
            comment = fields.get("commentaires_correctif") if "commentaires_correctif" in fields else fields.get("commentaire")
            if comment is not None:
                rec["commentaires_correctif"] = str(comment).strip()

            cursor = conn.cursor()
            stats = schema_v2.sync_members_to_v2(cursor, [rec], season_name)
            if not stats.get("purchases"):
                conn.rollback()
                msg = ("Une inscription plus prioritaire existe déjà pour cet adhérent "
                       "cette saison (statut/montant supérieurs).")
                print(f"[SQLITE] Ajout manuel refusé : {msg}")
                return False, msg
            conn.commit()
            print(f"[SQLITE] Adhérent manuel ajouté : {rec['user_lastName']} {rec['user_firstName']} "
                  f"({order_ref}, saison {season_name}).")
            return True, order_ref
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def list_contact_emails(cls) -> set:
        """Every member and payer address in the database (lower-cased)."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            emails = set()
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
                    print(f"[SQLITE] Date d'envoi d'e-mail enregistree pour l'achat #{purchase_id} : {date_str}")
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
                print(f"[SQLITE] Date d'envoi d'e-mail enregistree pour la commande {order_ref} : {date_str}")
                return True
            print(f"[SQLITE] Aucun achat trouve pour la commande {order_ref} (achat #{purchase_id})")
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
    ) -> Tuple[bool, str]:
        """
        Met à jour de manière ciblée les informations d'un adhérent :
        - Table users : badge_rouge, autonomie_bloc, email_primary, email_secondary, phone, sex…
        - Table purchases : tarif_name.
        Retourne (succès: bool, message: str) ; (False, message) pour un doublon d'adhérent, une autre erreur
        de base de données est annulée (rollback) et propagée.
        """
        if not fields:
            return False, "Aucun champ à mettre à jour."

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
            print(f"[SQLITE] Adhérent #{resolved_uid} mis à jour avec succès : {list(fields.keys())}")
            return True, ""
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, "Un autre adhérent avec les mêmes nom, prénom et date de naissance existe déjà."
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# Member fields written as trimmed text, and the yes/no fields with their default
_USER_TEXT_FIELDS = (
    "email_primary", "email_secondary", "phone", "licence_ffme", "address", "zip_code", "city",
    "emergency1_name", "emergency1_phone", "emergency2_name", "emergency2_phone", "hid_proxkey_date", "hid_proxkey_comment",
)
_USER_YES_NO_DEFAULTS = {"badge_rouge": "Non", "autonomie_bloc": "Non", "photo_auth": "Oui"}
_TRUE_TEXTS = ("oui", "true", "1", "yes")


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
        updates["birth_date"] = schema_v2.parse_iso_date(raw_birth_date) if raw_birth_date else ""
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
    if "hid_proxkey" in fields:
        value = fields["hid_proxkey"]
        has_key = value if isinstance(value, bool) else str(value or "Non").strip().lower() in _TRUE_TEXTS
        updates["hid_proxkey"] = "Oui" if has_key else "Non"
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
