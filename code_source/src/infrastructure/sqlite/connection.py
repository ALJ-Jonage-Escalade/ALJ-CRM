"""Local SQLite cache `database.db`: path, connections, schema, backups.

Shared by every repository of this package (members, seasons, planning, …): the
database path is a single class attribute, so set_db_path() redirects them all.
"""

from __future__ import annotations

import datetime
import glob
import logging
import os
import sqlite3
import time
from typing import Optional

from domain.club_emails import DEFAULT_SENDER_NAME
from infrastructure.sqlite import schema_v2
from paths import ROOT_DIR, data_root

logger = logging.getLogger("alj")

_DEFAULT_EMAIL_TEMPLATES = [
    ("Attestation standard", "Attestation de paiement escalade - Amicale Laïque de Jonage",
     "Bonjour {first_name},\n\nNous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage pour la saison.\n\nSportivement,\nL'équipe ALJ Escalade",
     "", DEFAULT_SENDER_NAME),
    ("Relance inscription", "Rappel : Finalisation de votre inscription ALJ Escalade",
     "Bonjour {first_name},\n\nSauf erreur de notre part, il nous manque encore certains éléments pour finaliser votre dossier d'adhésion pour la saison.\nNous vous invitons à vous connecter sur votre espace licencié pour vérifier le statut de votre certificat médical.\n\nSportivement,\nL'équipe ALJ Escalade",
     "", DEFAULT_SENDER_NAME)
]

_ATTESTATION_ECHEANCE_TEMPLATE = (
    "Attestation échéance",
    "Attestation de paiement et d'échéance - Amicale Laïque de Jonage",
    "Bonjour {first_name},\n\nNous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\nSportivement,\nL'équipe ALJ Escalade",
    "",  # empty sender: the sending account
    DEFAULT_SENDER_NAME
)

_COMPETITION_EMAIL_TEMPLATES = [
    (
        "Compétition - 1er Inscription",
        "[ALJ] Inscription Compétition {name_competition} du {date_competition}",
        "Bonjour,\nComme {first_name} l'a vu avec son entraineur, notre équipe encadrante lui propose de participer à la prochaine compétition d'escalade {name_competition} !\nCette compétition se déroule à la date du : {date_competition}.\nAfin de finaliser et régulariser son inscription, nous vous invitons à effectuer le règlement via notre page HelloAsso.\nVoici la démarche à suivre :\nRendez-vous sur le site HelloAsso <a href=\"https://www.helloasso.com/associations/amicale-laique-de-jonage/evenements/regularisation-inscription-competiteurs-2026-2027\">helloasso.com/</a>\n1- Procédez au règlement d'un montant de {montant_competition} €.\n2- Indiquer le nom de la compétition {name_competition}\n3- Indiquez le numéro de la compétition : {no_competition}\n4- Saisissez le numéro de licence de votre enfant : {num_licence}\n\nVoici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}\n\nMerci de réaliser cette démarche dans les meilleurs délais afin que l'inscription de votre enfant soit validée à temps auprès des organisateurs.\nSi vous rencontrez le moindre problème ou si vous avez des questions, n'hésitez pas à nous contacter en répondant à ce message.\nSportivement,\nL'équipe d'encadrement",
        "",  # empty sender: the sending account
        DEFAULT_SENDER_NAME
    ),
    (
        "Compétition - relance",
        "[ALJ] Inscription Compétition {name_competition} du {date_competition} [Relance]",
        "Bonjour,\nComme {first_name} l'a vu avec son entraineur, notre équipe encadrante lui propose de participer à la prochaine compétition d'escalade {name_competition} !\nCette compétition se déroule à la date du : {date_competition}.\nAfin de finaliser et régulariser son inscription, nous vous invitons à effectuer le règlement via notre page HelloAsso.\nVoici la démarche à suivre :\nRendez-vous sur le site HelloAsso <a href=\"https://www.helloasso.com/associations/amicale-laique-de-jonage/evenements/regularisation-inscription-competiteurs-2026-2027\">helloasso.com/</a>\n1- Procédez au règlement d'un montant de {montant_competition} €.\n2- Indiquer le nom de la compétition {name_competition}\n3- Indiquez le numéro de la compétition : {no_competition}\n4- Saisissez le numéro de licence de votre enfant : {num_licence}\n\nVoici le lien du groupe WhatsApp dédié à cette compétition : {whatsapp_link}\n\nMerci de réaliser cette démarche dans les meilleurs délais afin que l'inscription de votre enfant soit validée à temps auprès des organisateurs.\nSi vous rencontrez le moindre problème ou si vous avez des questions, n'hésitez pas à nous contacter en répondant à ce message.\n\nSportivement,\nL'équipe d'encadrement",
        "",  # empty sender: the sending account
        DEFAULT_SENDER_NAME
    )
]


# Correction request of the HelloAsso membership import (domain/members/correction_request.py): {problemes} lists the
# problems of each registration of the order; the family answers by e-mail
CORRECTION_REQUEST_EMAIL_TEMPLATE = (
    "Adhésion : informations à corriger",
    "Adhésion ALJ Escalade : informations à corriger",
    "Bonjour {first_name},\n\nMerci pour votre inscription à la section escalade de l'Amicale Laïque de Jonage. En préparant les "
    "licences FFME, nous avons relevé des informations qui semblent erronées ou manquantes :\n\n{problemes}\n\nPourriez-vous nous "
    "indiquer les bonnes valeurs en répondant simplement à cet e-mail ? Nous corrigerons le dossier nous-mêmes.\n\nSportivement,\n"
    "L'équipe ALJ Escalade",
    "",  # empty sender: the sending account
    DEFAULT_SENDER_NAME,
)

# Club keys (HID ProxKey) of the climbing wall, plans/club-keys.md: replicated to Firestore (cloud_sync TRACKED_TABLES).
# A code is unique whatever its case, archived keys included.
KEYS_DDL = (
    """CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL COLLATE NOCASE UNIQUE,
        status TEXT NOT NULL DEFAULT 'available',
        created_at TEXT, updated_at TEXT
    )""",
    # Who held a key and when; returned_on empty while held. One open assignment per key and per person.
    """CREATE TABLE IF NOT EXISTS key_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_id INTEGER NOT NULL REFERENCES keys(id),
        user_id INTEGER NOT NULL REFERENCES users(id),
        given_on TEXT NOT NULL,
        returned_on TEXT,
        comment TEXT NOT NULL DEFAULT '',
        return_comment TEXT NOT NULL DEFAULT '',
        by TEXT NOT NULL DEFAULT '',
        created_at TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_key_assignments_open_key ON key_assignments(key_id) WHERE returned_on IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_key_assignments_open_user ON key_assignments(user_id) WHERE returned_on IS NULL",
    # What else happened to a key: archived, restored, renamed, assignment_deleted
    """CREATE TABLE IF NOT EXISTS key_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_id INTEGER NOT NULL REFERENCES keys(id),
        type TEXT NOT NULL,
        date TEXT NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        by TEXT NOT NULL DEFAULT '',
        created_at TEXT
    )""",
)


def _add_missing_column(conn: sqlite3.Connection, cursor: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
    """Migration auto des BDD existantes : ajoute la colonne si elle manque."""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")  # noqa: S608 - noms de table/colonne littéraux du code
    except sqlite3.OperationalError:
        logger.info(f"[SQLITE] Ajout de la colonne '{column}' à la table {table}...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def _ensure_email_templates(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
    """Table email_templates, expéditeur par défaut et modèles livrés avec l'application."""
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS email_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        sender_email TEXT DEFAULT '',
        sender_name TEXT DEFAULT ''
    );
    """)
    _add_missing_column(conn, cursor, "email_templates", "sender_email", "TEXT DEFAULT ''")
    _add_missing_column(conn, cursor, "email_templates", "sender_name", "TEXT DEFAULT ''")
    # adherent | attestation | competition; empty for a template saved before kinds existed (inferred from its name)
    _add_missing_column(conn, cursor, "email_templates", "kind", "TEXT DEFAULT ''")
    # 1: the template a screen opens first for its kind (at most one per kind)
    _add_missing_column(conn, cursor, "email_templates", "is_default", "INTEGER DEFAULT 0")

    # The club's display name on the templates without one (an empty sender address stays empty: the sending account)
    for column, default in (("sender_name", DEFAULT_SENDER_NAME),):
        cursor.execute(f"SELECT COUNT(*) FROM email_templates WHERE {column} IS NULL OR TRIM({column}) = ''")  # noqa: S608 - noms de table/colonne littéraux du code
        if cursor.fetchone()[0] > 0:
            cursor.execute(f"UPDATE email_templates SET {column} = ? WHERE {column} IS NULL OR TRIM({column}) = ''", (default,))  # noqa: S608 - noms de table/colonne littéraux du code
            conn.commit()

    # Seed des templates par défaut si vides
    cursor.execute("SELECT COUNT(*) FROM email_templates")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
            INSERT INTO email_templates (name, subject, body, sender_email, sender_name) VALUES (?, ?, ?, ?, ?)
        """, _DEFAULT_EMAIL_TEMPLATES)
        conn.commit()

    # S'assurer de la présence du modèle d'email "Attestation échéance"
    try:
        cursor.execute("SELECT COUNT(*) FROM email_templates WHERE name = 'Attestation échéance' OR name = 'Attestation echéance' OR name = 'Attestation echeance'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO email_templates (name, subject, body, sender_email, sender_name)
                VALUES (?, ?, ?, ?, ?)
            """, _ATTESTATION_ECHEANCE_TEMPLATE)
            conn.commit()
    except Exception as e:
        logger.warning(f"[SQLITE] Impossible de s'assurer de la présence du modèle d'email 'Attestation échéance' : {e}")

    # S'assurer de la présence des modèles d'e-mails de compétition et de la demande de correction d'adhésion
    for template in [*_COMPETITION_EMAIL_TEMPLATES, CORRECTION_REQUEST_EMAIL_TEMPLATE]:
        cname = template[0]
        try:
            cursor.execute("SELECT COUNT(*) FROM email_templates WHERE name = ?", (cname,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO email_templates (name, subject, body, sender_email, sender_name)
                    VALUES (?, ?, ?, ?, ?)
                """, template)
                conn.commit()
        except Exception as e:
            logger.warning(f"[SQLITE] Impossible d'assurer la présence du modèle '{cname}' : {e}")


class SqliteDatabase:
    """Chemin, connexions et schéma de la base SQLite locale des adhérents."""
    _db_path: Optional[str] = None  # set_db_path(); else database.db of data_root()
    _database_setup_done = False

    @classmethod
    def get_db_path(cls) -> str:
        return cls._db_path or os.path.join(data_root(), "database.db")

    @classmethod
    def set_db_path(cls, path: str) -> None:
        cls._db_path = path
        cls._database_setup_done = False

    @classmethod
    def get_connection(cls, path: Optional[str] = None) -> sqlite3.Connection:
        """Connection to the application's database, or to the file at `path`."""
        conn = sqlite3.connect(path or cls.get_db_path(), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        # Les lignes écrasées par INSERT OR REPLACE déclenchent aussi les
        # déclencheurs de suppression (suivi des modifications pour Firestore).
        conn.execute("PRAGMA recursive_triggers=ON")
        return conn

    @classmethod
    def setup_database(cls, force: bool = False) -> None:
        """Initialise la base de données de l'application (une fois par processus, sauf `force`)."""
        if not force and cls._database_setup_done:
            return
        cls.apply_schema(cls.get_db_path())
        cls._database_setup_done = True

    @classmethod
    def apply_schema(cls, path: str) -> None:
        """Creates or upgrades the tables of the SQLite file at `path` (the cache, a new cache being built, a copy),
        without changing the file the application uses."""
        logger.debug(f"[SQLITE] Initialisation de la BDD à l'emplacement : {path}")
        conn = cls.get_connection(path)
        cursor = conn.cursor()

        # Schéma v2 : users / orders / purchases / purchase_options (plus de tables legacy adherents*)
        schema_v2.ensure_v2_schema(cursor)

        # Création des tables de saisons
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS seasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            is_active INTEGER DEFAULT 0
        );
        """)

        # Insérer les saisons par défaut
        cursor.execute("INSERT OR IGNORE INTO seasons (name, is_active) VALUES ('2025-2026', 0)")
        cursor.execute("INSERT OR IGNORE INTO seasons (name, is_active) VALUES ('2026-2027', 1)")

        # Création de la table de cache géocodage
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS geocache (
            address TEXT PRIMARY KEY,
            lat REAL,
            lon REAL
        );
        """)

        # Création de la table de planning
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS planning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            groupe TEXT NOT NULL,
            type TEXT,
            categorie_age TEXT,
            whatsapp_link TEXT,
            jour TEXT,
            horaires TEXT,
            encadrants TEXT,
            helloasso_tarifs TEXT DEFAULT '[]',
            naissance_min TEXT DEFAULT '',
            naissance_max TEXT DEFAULT '',
            seance_autonome INTEGER DEFAULT 0
        );
        """)
        _add_missing_column(conn, cursor, "planning", "helloasso_tarifs", "TEXT DEFAULT '[]'")
        # Bornes de date de naissance par groupe, utilisées pour le contrôle d'âge : un adulte
        # (18 ans révolus au 01/09) ne peut pas souscrire à un groupe enfants / collège / lycée,
        # et l'année de naissance doit correspondre aux années du tarif HelloAsso.
        _add_missing_column(conn, cursor, "planning", "naissance_min", "TEXT DEFAULT ''")
        _add_missing_column(conn, cursor, "planning", "naissance_max", "TEXT DEFAULT ''")
        # Case « Séance autonome » : les inscrits du créneau figurent sur la fiche de présence autonome
        _add_missing_column(conn, cursor, "planning", "seance_autonome", "INTEGER DEFAULT 0")

        # Document de santé FFME : information associée à une personne pour une saison
        # donnée, stockée au niveau de l'achat (purchases).
        _add_missing_column(conn, cursor, "purchases", "document_sante", "TEXT DEFAULT ''")
        # HelloAsso membership import (plans/helloasso-membership-import.md): the registration a purchase comes from
        # and the last values read on HelloAsso (status, amount, tariff), to tell a change on HelloAsso from a CRM edit
        for column, ddl in (("helloasso_item_id", "INTEGER"), ("helloasso_status", "TEXT"),
                            ("helloasso_amount", "REAL"), ("helloasso_tarif", "TEXT")):
            _add_missing_column(conn, cursor, "purchases", column, ddl)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_purchases_helloasso_item ON purchases(helloasso_item_id)"
                       " WHERE helloasso_item_id IS NOT NULL")

        _ensure_email_templates(conn, cursor)
        for statement in KEYS_DDL:
            cursor.execute(statement)

        # Table de réglages clé/valeur, plus écrite par l'application (les réglages sont dans la
        # collection Firestore `app_settings`) : conservée pour la réplication de crm_app_settings.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)

        # Schema version (PRAGMA user_version): 0 for a new file, tagged v2 here
        cursor.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]
        if current_version == 1:
            conn.close()
            # The cache is rebuilt from Firestore at the current schema: a v1 file is a stray copy
            raise RuntimeError(f"Base SQLite au schéma v1 non prise en charge ({path}) : supprimez ce fichier, "
                               "le cache est reconstruit depuis Firestore.")
        if current_version == 0:
            cursor.execute(f"PRAGMA user_version = {schema_v2.SCHEMA_TARGET_VERSION}")
            logger.info(f"[SQLITE] Base neuve taguée en version {schema_v2.SCHEMA_TARGET_VERSION} (schéma v2 natif).")
        schema_v2.drop_former_user_columns(cursor)
        # Flat member view: created again on every start to follow the code's definition
        schema_v2.recreate_member_flat_view(cursor)

        conn.commit()
        conn.close()
        logger.debug("[SQLITE] Initialisation et vérification du schéma d'adhérents accomplies.")

    @classmethod
    def check_readable(cls) -> Optional[str]:
        """None when the database file exists and can be queried, else the reason."""
        db_path = cls.get_db_path()
        if not os.path.exists(db_path):
            return "database file not found"
        try:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            finally:
                conn.close()
            return None
        except Exception as e:
            return str(e)

    @classmethod
    def create_db_backup(cls) -> None:
        """Crée une sauvegarde de sécurité horodatée de la base de données dans archive/db avec rétention de 10 jours.

        Pointless with Firestore replication (the cache is rebuilt from it, and ROOT_DIR, « / » on Cloud Run, is not
        writable): the caller skips it then. Optional: a failure never blocks the operation in progress.
        """
        db_path = cls.get_db_path()
        if not os.path.exists(db_path):
            return

        try:
            backup_dir = os.path.join(ROOT_DIR, "archive", "db")
            os.makedirs(backup_dir, exist_ok=True)

            # Éviter de sur-sauvegarder si la base n'a pas changé ou si la dernière sauvegarde a moins de 5 secondes
            backups = glob.glob(os.path.join(backup_dir, "database_backup_*.db"))
            if backups:
                backups.sort(key=os.path.getmtime, reverse=True)
                latest_backup = backups[0]
                # Si la base de données n'a pas été modifiée depuis le dernier backup, on ignore la sauvegarde
                if os.path.getmtime(db_path) <= os.path.getmtime(latest_backup):
                    return
                if time.time() - os.path.getmtime(latest_backup) < 5:
                    return

            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"database_backup_{now_str}.db")

            # API backup SQLite : snapshot cohérent (inclut le journal WAL), contrairement
            # à une copie fichier brute qui peut capturer un état incohérent.
            src_conn = cls.get_connection()
            dst_conn = sqlite3.connect(backup_path)
            src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()
            logger.info(f"[SQLITE] Sauvegarde de BDD créée : {os.path.basename(backup_path)}")

            # Gérer la rétention : conserver toutes les sauvegardes des 10 derniers jours
            backups = glob.glob(os.path.join(backup_dir, "database_backup_*.db"))
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=10)

            for bk in backups:
                try:
                    mtime = os.path.getmtime(bk)
                    file_date = datetime.datetime.fromtimestamp(mtime)
                    if file_date < cutoff_date:
                        os.remove(bk)
                        logger.info(f"[SQLITE] Sauvegarde BDD expirée (>10 jours) purgée : {os.path.basename(bk)}")
                except Exception as pe:
                    logger.warning(f"[SQLITE] Impossible de purger l'ancien backup {bk} : {pe}")

        except Exception as e:
            logger.warning(f"[SQLITE] Impossible de créer la sauvegarde de BDD : {e}")
