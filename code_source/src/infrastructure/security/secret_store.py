"""The club's credentials (Google OAuth, SMTP, HelloAsso…): environment variables and the .env files.

On Cloud Run, the Google OAuth values renewed from the app (refresh token, client, account) also live in a
document of the database (infrastructure/firestore/server_credentials.py, handed over by server.py at startup through
use_credentials_document): an instance's environment is lost on restart and not shared with the other instances, so
that document is read first and every renewal is written to it. Received rather than imported: the Firestore client
itself needs these secrets.
"""

from __future__ import annotations

import datetime
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Protocol

from infrastructure import runtime_env

logger = logging.getLogger("alj")

# Secret name -> field of the credentials document
FIRESTORE_FIELDS: Dict[str, str] = {
    "GMAIL_REFRESH_TOKEN": "refresh_token",
    "GMAIL_USER_EMAIL": "user_email",
    "GMAIL_CLIENT_ID": "client_id",
    "GMAIL_CLIENT_SECRET": "client_secret",
}
RELOAD_AFTER_FAILURE = 60.0  # seconds before reading the Firestore document again after a failed read


class SecretPersistenceError(RuntimeError):
    """A secret could not be saved where it must survive a restart (Firestore, on Cloud Run): nothing was changed."""


class CredentialsDocument(Protocol):
    """Where the Google OAuth values are kept on Cloud Run."""

    def read(self) -> Dict[str, Any]: ...  # Any: the document's fields as stored

    def update(self, fields: Dict[str, str]) -> None: ...



_lock = threading.Lock()
_firestore_values: Dict[str, str] = {}  # fields of the Firestore document, once read
_firestore_loaded = False
_last_failed_load = -RELOAD_AFTER_FAILURE  # time.monotonic() of the last failed read
_credentials_document: Optional[CredentialsDocument] = None


def use_credentials_document(document: Optional[CredentialsDocument]) -> None:
    """Called once at startup (server.py). Without one, on Cloud Run, the environment answers alone and saving fails."""
    global _credentials_document, _firestore_loaded, _last_failed_load
    with _lock:
        _credentials_document = document
        _firestore_loaded = False
        _last_failed_load = -RELOAD_AFTER_FAILURE


def _load_firestore_values() -> None:
    """Reads the Firestore document once; after a failure, again on a call RELOAD_AFTER_FAILURE seconds later."""
    global _firestore_values, _firestore_loaded, _last_failed_load
    with _lock:
        if _firestore_loaded or time.monotonic() - _last_failed_load < RELOAD_AFTER_FAILURE:
            return
        try:
            if _credentials_document is None:
                raise RuntimeError("no credentials document (secret_store.use_credentials_document not called)")
            doc = _credentials_document.read()
        except Exception:  # Firestore or its access token unreachable: the environment answers meanwhile
            _last_failed_load = time.monotonic()
            # The delay only, never a secret value
            logger.warning("Chargement des secrets Firestore impossible, nouvel essai dans %d s",  # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
                           RELOAD_AFTER_FAILURE, exc_info=True)
            return
        fields = set(FIRESTORE_FIELDS.values())
        _firestore_values = {k: str(v).strip() for k, v in (doc or {}).items() if k in fields and v}
        _firestore_loaded = True


def _write_env_file(key: str, value: str) -> None:
    env_path = runtime_env.local_env_file()
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
        if field and runtime_env.is_cloud_run():
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
        if runtime_env.is_cloud_run():
            fields = {FIRESTORE_FIELDS[key]: value for key, value in values.items() if key in FIRESTORE_FIELDS}
            if fields:
                try:
                    if _credentials_document is None:
                        raise RuntimeError("no credentials document (secret_store.use_credentials_document not called)")
                    _credentials_document.update({
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
