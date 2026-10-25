"""Members (schema v2: users / orders / purchases / purchase_options): reads, imports, edits."""

from __future__ import annotations

import datetime
import os
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from domain.constants import CORRECTIVE_MAP
from infrastructure.sqlite import schema_v2
from infrastructure.sqlite.connection import DB_WRITE_ERROR, SqliteDatabase

EXTRA_COLUMNS = {
    "is_modified": "TEXT DEFAULT 'Non'",
    "commentaires_correctif": "TEXT DEFAULT ''",
    "badge_rouge": "TEXT DEFAULT 'Non'",
    "autonomie_bloc": "TEXT DEFAULT 'Non'",
    "raw_passports": "TEXT DEFAULT ''",
    "raw_diplomas": "TEXT DEFAULT ''",
    "parental_auth_autonomous": "TEXT DEFAULT 'Non'", # Nouveau !
    "parental_auth_family": "TEXT DEFAULT 'Non'",     # Nouveau !
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
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors du chargement des données : {e}")
            return []
        finally:
            conn.close()

    @classmethod
    def _load_data_from_compat_view(cls, conn, season_filter: str) -> list:
        """Phase 2 — Chargement via v_adherents_legacy (schéma cible v2). Mêmes clés que le chemin legacy."""
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

    @classmethod
    def get_members(cls, season_filter: str = "2026-2027") -> list:
        """
        Phase 4 — Lecture typée canonique : retourne des objets Member construits
        depuis la lecture bilingue (vue de compatibilité + Member.from_dict).
        API recommandée pour les nouveaux consommateurs.
        """
        from domain.members.models import Member
        return [Member.from_dict(row) for row in cls.load_direct_data(season_filter=season_filter)]
    # One row per purchase (users ⨝ orders ⨝ purchases ⨝ seasons), the fields of the web member pages
    _MEMBER_ROWS_SQL = """
        SELECT u.id AS user_id, p.id AS purchase_id,
               u.last_name, u.first_name, u.birth_date, u.gender,
               u.address, u.zip_code, u.city, u.phone, u.email_primary, u.email_secondary,
               u.emergency1_name, u.emergency1_phone, u.emergency2_name, u.emergency2_phone,
               u.licence_ffme, u.health_commitment, u.photo_auth, u.badge_rouge, u.autonomie_bloc,
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
    def export_to_excel(cls, file_path: str) -> bool:
        """
        Phase 9 — Exporte les adhérents de la saison active vers un fichier Excel,
        via Member.to_dict() (adaptateur vers le format colonnes historique).
        """
        SqliteDatabase.setup_database()
        members = cls.get_members(season_filter="2026-2027")

        excel_rows = []
        for m in members:
            d = m.to_dict()
            excel_row = {}
            # Reconstituer toutes les colonnes d'origine de CORRECTIVE_MAP
            for excel_col, cache_key in CORRECTIVE_MAP.items():
                excel_row[excel_col] = d.get(cache_key, "")

            # Ajouter les colonnes supplémentaires indispensables
            for col_key in EXTRA_COLUMNS.keys():
                excel_row[col_key] = d.get(col_key, "")

            excel_rows.append(excel_row)

        try:
            df = pd.DataFrame(excel_rows)
            # S'assurer que le dossier parent existe
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            from exports.spreadsheet_safety import safe_to_excel
            safe_to_excel(df, file_path, index=False)  # member data must never become a formula
            print(f"💾 [SQLITE] Base de données exportée avec succès vers Excel : {file_path}")
            return True
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors de l'exportation de la base de données vers Excel : {e}")
            return False

    @classmethod
    def upsert_members(cls, members: list, season_name: str = "2026-2027") -> int:
        """
        Phase 5 - Insere ou met a jour un lot d'adherents dans le schema v2
        (users / orders / purchases / purchase_options).
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        inserted_count = 0
        try:
            cursor = conn.cursor()
            stats = schema_v2.sync_members_to_v2(cursor, members, season_name)
            inserted_count = stats["purchases"]
            conn.commit()
            print(f"[SQLITE] Synchro reussie : {inserted_count} adhesions enregistrees/mises a jour "
                  f"pour la saison {season_name}. (v2: {stats})")
        except Exception as e:
            print(f"[SQLITE] Erreur lors de l'upsert des adherents : {e}")
            conn.rollback()
        finally:
            conn.close()
        return inserted_count

    @classmethod
    def update_member_in_db(cls, original_order_ref: str, original_last_name: str, original_first_name: str, updated_fields: dict, comment_text: str):
        """
        Phase 5 - Met a jour un adherent dans le schema v2 :
        champs personnels -> users, champs de saison -> purchases (avec options).
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            from domain.utils import normalize_name
            cursor.execute("""
                SELECT p.user_id FROM purchases p
                JOIN orders o ON o.id = p.order_id
                WHERE o.order_ref = ?
            """, (original_order_ref.strip(),))
            rows = cursor.fetchall()
            user_id = None
            if rows:
                t_last = normalize_name(original_last_name)
                t_first = normalize_name(original_first_name)
                for r in rows:
                    u = cursor.execute("SELECT last_name, first_name FROM users WHERE id=?", (r["user_id"],)).fetchone()
                    if u and normalize_name(u["last_name"]) == t_last and normalize_name(u["first_name"]) == t_first:
                        user_id = r["user_id"]
                        break
                if user_id is None:
                    # Fallback famille : premier utilisateur de la commande
                    user_id = rows[0]["user_id"]
            if user_id is None:
                conn.close()
                return False, f"Aucun adherent correspondant trouve pour {original_last_name} {original_first_name}."
            schema_v2.apply_member_update(cursor, user_id, original_order_ref, updated_fields, comment_text)
            conn.commit()
            print(f"[SQLITE] Adherent {original_last_name} {original_first_name} mis a jour avec succes (v2).")
            return True, ""
        except Exception as e:
            print(f"[SQLITE] Erreur lors de la mise a jour de l'adherent : {e}")
            conn.rollback()
            return False, DB_WRITE_ERROR
        finally:
            conn.close()

    @classmethod
    def add_manual_member(cls, fields: dict, season_name: str = "2026-2027") -> tuple:
        """
        Ajoute manuellement un adhérent dans le schéma v2 (users + orders + purchases),
        en synthétisant une commande « MANUEL-... » équivalente à une inscription HelloAsso.
        Champs attendus : last_name, first_name, birth_date ('JJ/MM/AAAA' ou ISO), gender,
        phone, email_primary, address, zip_code, city, tarif_name, status, amount.
        Retourne (True, order_ref) ou (False, message d'erreur).
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            import datetime as _dt
            from infrastructure.sqlite.schema_v2 import DOB_COLUMN

            now = _dt.datetime.now()
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
                DOB_COLUMN: str(fields.get("birth_date") or "").strip(),
                "champ_Sexe": str(fields.get("gender") or "").strip(),
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
        except Exception as e:
            print(f"[SQLITE] Erreur lors de l'ajout manuel de l'adherent : {e}")
            conn.rollback()
            return False, DB_WRITE_ERROR
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
    def correct_member_address(cls, first_name: str, last_name: str, address: str, zip_code: str,
                               city: str, geocode: Optional[Tuple[str, float, float]] = None):
        """Overwrite a member's address (matched by name) and optionally cache its
        (full_address, lat, lon) geocode, in a single transaction."""
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        try:
            conn.execute(
                "UPDATE users SET address = ?, zip_code = ?, city = ? "
                "WHERE UPPER(TRIM(first_name)) = UPPER(TRIM(?)) "
                "AND UPPER(TRIM(last_name)) = UPPER(TRIM(?))",
                (address, zip_code, city, first_name, last_name),
            )
            if geocode:
                conn.execute("""
                    INSERT INTO geocache (address, lat, lon) VALUES (?, ?, ?)
                    ON CONFLICT(address) DO UPDATE SET lat = excluded.lat, lon = excluded.lon
                """, geocode)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def update_email_sent_date(cls, order_ref: str, last_name: str, first_name: str, date_str: str, purchase_id: Optional[int] = None) -> bool:
        """Phase 5 - Met a jour la date d'envoi d'e-mail sur les achats v2 de la commande."""
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
        except Exception as e:
            print(f"[SQLITE] Erreur lors de la mise a jour de la date d'envoi d'e-mail : {e}")
            conn.rollback()
            return False
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
        - Table users : badge_rouge, autonomie_bloc, email_primary, email_secondary, phone.
        - Table purchases : tarif_name.
        Retourne (succès: bool, message: str).
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

            # 1. Mise à jour de la table users
            user_updates = {}
            if "badge_rouge" in fields:
                user_updates["badge_rouge"] = str(fields["badge_rouge"] or "Non").strip()
            if "autonomie_bloc" in fields:
                user_updates["autonomie_bloc"] = str(fields["autonomie_bloc"] or "Non").strip()
            if "email_primary" in fields:
                user_updates["email_primary"] = str(fields["email_primary"] or "").strip()
            if "email_secondary" in fields:
                user_updates["email_secondary"] = str(fields["email_secondary"] or "").strip()
            if "phone" in fields:
                user_updates["phone"] = str(fields["phone"] or "").strip()
            if "licence_ffme" in fields:
                user_updates["licence_ffme"] = str(fields["licence_ffme"] or "").strip()
            if "address" in fields:
                user_updates["address"] = str(fields["address"] or "").strip()
            if "zip_code" in fields:
                user_updates["zip_code"] = str(fields["zip_code"] or "").strip()
            if "city" in fields:
                user_updates["city"] = str(fields["city"] or "").strip()

            if user_updates and resolved_uid is not None:
                sets = [f'"{col}" = ?' for col in user_updates.keys()]
                sets.append('updated_at = ?')
                params = list(user_updates.values()) + [now_iso, int(resolved_uid)]
                cursor.execute(f'UPDATE users SET {", ".join(sets)} WHERE id = ?', params)  # noqa: S608 - colonnes de la liste fixe ci-dessus

            # 2. Mise à jour de la table purchases (créneau / tarif)
            if "tarif_name" in fields:
                new_tarif = str(fields["tarif_name"] or "").strip()
                if new_tarif:
                    if purchase_id:
                        cursor.execute("""
                            UPDATE purchases
                            SET tarif_name = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE id = ?
                        """, (new_tarif, now_iso, int(purchase_id)))
                    elif order_ref and resolved_uid:
                        cursor.execute("""
                            UPDATE purchases
                            SET tarif_name = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE user_id = ? AND order_id IN (SELECT id FROM orders WHERE order_ref = ?)
                        """, (new_tarif, now_iso, int(resolved_uid), str(order_ref).strip()))
                    elif resolved_uid:
                        cursor.execute("""
                            UPDATE purchases
                            SET tarif_name = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE user_id = ?
                        """, (new_tarif, now_iso, int(resolved_uid)))

            # 3. Mise à jour du statut de l'adhésion (purchases & orders)
            if "status" in fields:
                new_status = str(fields["status"] or "").strip()
                if new_status:
                    norm = "Validé" if new_status.lower() in ("processed", "validated", "validé", "valide") else ("Annulé" if new_status.lower() in ("annulé", "annule", "canceled", "cancelled") else new_status.title())
                    if purchase_id:
                        cursor.execute("""
                            UPDATE purchases
                            SET status = ?, status_normalized = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE id = ?
                        """, (new_status, norm, now_iso, int(purchase_id)))
                    elif order_ref and resolved_uid:
                        cursor.execute("""
                            UPDATE purchases
                            SET status = ?, status_normalized = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE user_id = ? AND order_id IN (SELECT id FROM orders WHERE order_ref = ?)
                        """, (new_status, norm, now_iso, int(resolved_uid), str(order_ref).strip()))
                    elif resolved_uid:
                        cursor.execute("""
                            UPDATE purchases
                            SET status = ?, status_normalized = ?, updated_at = ?, is_modified = 'Oui'
                            WHERE user_id = ?
                        """, (new_status, norm, now_iso, int(resolved_uid)))

                    if order_ref:
                        cursor.execute("""
                            UPDATE orders
                            SET status = ?, status_normalized = ?, updated_at = ?
                            WHERE order_ref = ?
                        """, (new_status, norm, now_iso, str(order_ref).strip()))
                    elif purchase_id:
                        cursor.execute("""
                            UPDATE orders
                            SET status = ?, status_normalized = ?, updated_at = ?
                            WHERE id = (SELECT order_id FROM purchases WHERE id = ?)
                        """, (new_status, norm, now_iso, int(purchase_id)))

            # 4. Mise à jour des commentaires / correctifs (purchases)
            comment_val = None
            if "commentaires_correctif" in fields:
                comment_val = fields["commentaires_correctif"]
            elif "commentaire" in fields:
                comment_val = fields["commentaire"]
            elif "comment" in fields:
                comment_val = fields["comment"]

            if comment_val is not None:
                new_comment = str(comment_val or "").strip()
                if purchase_id:
                    cursor.execute("""
                        UPDATE purchases
                        SET commentaires_correctif = ?, updated_at = ?, is_modified = 'Oui'
                        WHERE id = ?
                    """, (new_comment, now_iso, int(purchase_id)))
                elif order_ref and resolved_uid:
                    cursor.execute("""
                        UPDATE purchases
                        SET commentaires_correctif = ?, updated_at = ?, is_modified = 'Oui'
                        WHERE user_id = ? AND order_id IN (SELECT id FROM orders WHERE order_ref = ?)
                    """, (new_comment, now_iso, int(resolved_uid), str(order_ref).strip()))
                elif resolved_uid:
                    cursor.execute("""
                        UPDATE purchases
                        SET commentaires_correctif = ?, updated_at = ?, is_modified = 'Oui'
                        WHERE user_id = ?
                    """, (new_comment, now_iso, int(resolved_uid)))

            conn.commit()
            print(f"[SQLITE] Adhérent #{resolved_uid} mis à jour avec succès : {list(fields.keys())}")
            return True, ""
        except Exception as e:
            print(f"❌ [SQLITE] Erreur lors de la mise à jour de l'adhérent : {e}")
            conn.rollback()
            return False, DB_WRITE_ERROR
        finally:
            conn.close()
