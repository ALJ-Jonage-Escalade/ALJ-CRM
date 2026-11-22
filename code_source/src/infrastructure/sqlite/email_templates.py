"""E-mail templates (`email_templates` table) of the communication page."""

from __future__ import annotations

from typing import Optional

from domain.club_emails import DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME
from infrastructure.sqlite.connection import SqliteDatabase


class EmailTemplateRepository:
    @classmethod
    def get_email_templates(cls) -> list:
        """
        Récupère l'ensemble des templates d'emails enregistrés en BDD.
        Retourne une liste de dicts : [{"name": ..., "subject": ..., "body": ..., "sender_email": ..., "sender_name": ...,
        "kind": ...}] (kind vide : modèle enregistré avant les types)
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, subject, body, sender_email, sender_name, kind FROM email_templates ORDER BY name ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def save_email_template(cls, name: str, subject: str, body: str, sender_email: str = "", sender_name: str = "",
                            old_name: Optional[str] = None, kind: str = "") -> None:
        """
        Enregistre ou met à jour un template d'email dans la BDD
        (avec son adresse et son nom d'affichage d'expédition, et son type : adherent, attestation ou competition).
        Si old_name est fourni et différent de name, le template existant est renommé.
        Une adresse / un nom vide retombe sur les valeurs par défaut du club.
        A database failure is rolled back and raised.
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            sender = (sender_email or "").strip() or DEFAULT_SENDER_EMAIL
            sname = (sender_name or "").strip() or DEFAULT_SENDER_NAME
            new_name = name.strip()
            clean_old = (old_name or "").strip()

            if clean_old and clean_old != new_name:
                cursor.execute("""
                    UPDATE email_templates
                    SET name = ?, subject = ?, body = ?, sender_email = ?, sender_name = ?, kind = ?
                    WHERE name = ?
                """, (new_name, subject.strip(), body.strip(), sender, sname, kind, clean_old))
                if cursor.rowcount > 0:
                    conn.commit()
                    return

            cursor.execute("""
                INSERT INTO email_templates (name, subject, body, sender_email, sender_name, kind)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET subject = excluded.subject, body = excluded.body,
                    sender_email = excluded.sender_email, sender_name = excluded.sender_name, kind = excluded.kind
            """, (new_name, subject.strip(), body.strip(), sender, sname, kind))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def delete_email_template(cls, name: str) -> bool:
        """
        Supprime un template d'email de la BDD : False when no template has this name.
        A database failure is rolled back and raised.
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM email_templates WHERE name = ?", (name.strip(),))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
