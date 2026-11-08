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
        Retourne une liste de dicts : [{"name": ..., "subject": ..., "body": ..., "sender_email": ..., "sender_name": ...}]
        """
        SqliteDatabase.setup_database()
        conn = SqliteDatabase.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, subject, body, sender_email, sender_name FROM email_templates ORDER BY name ASC")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @classmethod
    def save_email_template(cls, name: str, subject: str, body: str, sender_email: str = "", sender_name: str = "", old_name: Optional[str] = None) -> None:
        """
        Enregistre ou met à jour un template d'email dans la BDD
        (avec son adresse et son nom d'affichage d'expédition).
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
                    SET name = ?, subject = ?, body = ?, sender_email = ?, sender_name = ?
                    WHERE name = ?
                """, (new_name, subject.strip(), body.strip(), sender, sname, clean_old))
                if cursor.rowcount > 0:
                    conn.commit()
                    return

            cursor.execute("""
                INSERT INTO email_templates (name, subject, body, sender_email, sender_name)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET subject = excluded.subject, body = excluded.body,
                    sender_email = excluded.sender_email, sender_name = excluded.sender_name
            """, (new_name, subject.strip(), body.strip(), sender, sname))
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
