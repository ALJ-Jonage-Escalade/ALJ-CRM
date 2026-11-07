"""The club's credentials (Google OAuth, SMTP, HelloAsso…): environment variables and the .env files.

On Cloud Run, the Google OAuth values renewed from the app (refresh token, client, account) also live in the
Firestore document server_credentials/google_oauth: an instance's environment is lost on restart and not shared
with the other instances, so that document is read first and every renewal is written to it.
"""

from __future__ import annotations

import datetime
import logging
import os
import threading
import time
from typing import Dict

from dotenv import load_dotenv

from paths import CODE_ROOT, ROOT_DIR

logger = logging.getLogger("alj")

# Charger le .env embarqué et surcharger avec le .env local
load_dotenv(os.path.join(CODE_ROOT, ".env"))
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=True)

FIRESTORE_COLLECTION = "server_credentials"
FIRESTORE_DOCUMENT = "google_oauth"
# Secret name -> field of server_credentials/google_oauth
FIRESTORE_FIELDS: Dict[str, str] = {
    "GMAIL_REFRESH_TOKEN": "refresh_token",
    "GMAIL_USER_EMAIL": "user_email",
    "GMAIL_CLIENT_ID": "client_id",
    "GMAIL_CLIENT_SECRET": "client_secret",
}
RELOAD_AFTER_FAILURE = 60.0  # seconds before reading the Firestore document again after a failed read


class SecretPersistenceError(RuntimeError):
    """A secret could not be saved where it must survive a restart (Firestore, on Cloud Run): nothing was changed."""


_lock = threading.Lock()
_firestore_values: Dict[str, str] = {}  # fields of the Firestore document, once read
_firestore_loaded = False
_last_failed_load = -RELOAD_AFTER_FAILURE  # time.monotonic() of the last failed read


def _on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE") or os.environ.get("K_CONFIGURATION"))


def _load_firestore_values() -> None:
    """Reads the Firestore document once; after a failure, again on a call RELOAD_AFTER_FAILURE seconds later."""
    global _firestore_values, _firestore_loaded, _last_failed_load
    with _lock:
        if _firestore_loaded or time.monotonic() - _last_failed_load < RELOAD_AFTER_FAILURE:
            return
        try:
            from infrastructure.firestore.client import FirestoreClient
            doc = FirestoreClient.get_document(FIRESTORE_COLLECTION, FIRESTORE_DOCUMENT)
        except Exception:  # Firestore or its access token unreachable: the environment answers meanwhile
            _last_failed_load = time.monotonic()
            # Collection name and delay only, never a secret value
            logger.warning("Chargement des secrets Firestore (%s) impossible, nouvel essai dans %d s",  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                           FIRESTORE_COLLECTION, RELOAD_AFTER_FAILURE, exc_info=True)
            return
        fields = set(FIRESTORE_FIELDS.values())
        _firestore_values = {k: str(v).strip() for k, v in (doc or {}).items() if k in fields and v}
        _firestore_loaded = True


def _env_file_path() -> str:
    """The .env that a local server reads last (ROOT_DIR overrides CODE_ROOT, see load_dotenv above)."""
    root_env = os.path.join(ROOT_DIR, ".env")
    return root_env if os.path.exists(root_env) else os.path.join(CODE_ROOT, ".env")


def _write_env_file(key: str, value: str) -> None:
    env_path = _env_file_path()
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    new_lines = []
    updated = False
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f"{key}={value}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class SecretStore:
    """Reads and saves the club's credentials (see the module docstring for where they live)."""

    @staticmethod
    def get_secret(key: str) -> str:
        """The secret's value, "" when unknown: Firestore first for the Google OAuth values on Cloud Run, then
        the environment (.env included)."""
        field = FIRESTORE_FIELDS.get(key)
        if field and _on_cloud_run():
            _load_firestore_values()
            value = _firestore_values.get(field)
            if value:
                return value
        return os.getenv(key, "").strip()

    @staticmethod
    def set_secret(key: str, value: str) -> None:
        """Saves one secret, see set_secrets."""
        SecretStore.set_secrets({key: value})

    @staticmethod
    def set_secrets(values: Dict[str, str]) -> None:
        """Saves secrets for this process and the next ones: in Firestore on Cloud Run (Google OAuth values, in one
        write so they never get mixed with older ones), in the .env file locally. Raises SecretPersistenceError,
        without changing anything, when they can't be kept."""
        if _on_cloud_run():
            fields = {FIRESTORE_FIELDS[key]: value for key, value in values.items() if key in FIRESTORE_FIELDS}
            if fields:
                try:
                    from infrastructure.firestore.client import FirestoreClient
                    FirestoreClient.update_fields(FIRESTORE_COLLECTION, FIRESTORE_DOCUMENT, {
                        **fields, "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                except Exception as e:  # Firestore or its access token unreachable
                    # Key names only, never the values
                    raise SecretPersistenceError(f"Enregistrement de {', '.join(values)} dans Firestore impossible : {e}") from e
                with _lock:
                    _firestore_values.update(fields)
            # The instance's .env is lost on restart: the environment is enough for this process
        else:
            try:
                for key, value in values.items():
                    _write_env_file(key, value)
            except OSError as e:
                raise SecretPersistenceError(f"Enregistrement de {key} dans le fichier .env impossible : {e}") from e
        os.environ.update(values)
