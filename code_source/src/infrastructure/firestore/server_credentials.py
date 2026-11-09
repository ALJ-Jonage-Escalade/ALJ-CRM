"""The Firestore document server_credentials/google_oauth: where SecretStore keeps the club's Google OAuth values on
Cloud Run (an instance's environment is lost on restart and not shared with the other instances).
server.py hands it to SecretStore at startup (secret_store.use_credentials_document)."""

from __future__ import annotations

from typing import Any, Dict

from infrastructure.firestore.client import FirestoreClient

COLLECTION = "server_credentials"
DOCUMENT = "google_oauth"


class FirestoreCredentialsDocument:
    """secret_store.CredentialsDocument over Firestore."""

    def read(self) -> Dict[str, Any]:  # Any: the document's fields as stored
        return FirestoreClient.get_document(COLLECTION, DOCUMENT) or {}

    def update(self, fields: Dict[str, str]) -> None:
        FirestoreClient.update_fields(COLLECTION, DOCUMENT, fields)
