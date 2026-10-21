"""Application settings (key/value) in the Firestore `app_settings` collection.

Single store for every setting: HelloAsso annual campaign, WhatsApp invitation text,
results batch notification e-mail and status, webhook notification marks…

Settings formerly saved in the SQLite cache table `app_settings` live in Firestore as
`crm_app_settings` documents (see cloud_database). A key missing from `app_settings` is
read from there once and copied over, so no separate data migration is needed.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore.cloud_database import DEL_FIELD, collection_for, doc_id_for

logger = logging.getLogger("alj")

COLLECTION = "app_settings"
LEGACY_COLLECTION = collection_for("app_settings")

WHATSAPP_TEMPLATE = "whatsapp_template"


class AppSettingsRepository:
    """Lecture / écriture des réglages applicatifs (toutes les méthodes sont des classmethods)."""

    @classmethod
    def _legacy_value(cls, key: str) -> Optional[str]:
        """Value of `key` in the former SQLite-replicated collection, or None."""
        doc = FirestoreClient.get_document(LEGACY_COLLECTION, doc_id_for([key]))
        if not doc or doc.get(DEL_FIELD) or doc.get("value") is None:
            return None
        return str(doc["value"])

    @classmethod
    def get(cls, key: str, default: Optional[str] = "") -> Optional[str]:
        """Value of the setting, or `default` when it is missing or blank."""
        doc = FirestoreClient.get_document(COLLECTION, str(key))
        if doc is not None:
            value = doc.get("value")
        else:
            value = cls._legacy_value(key)
            if value is not None:
                cls.save(key, value)
                logger.info("Setting %s copied from %s to %s", key, LEGACY_COLLECTION, COLLECTION)
        if value is None or not str(value).strip():
            return default
        return str(value)

    @classmethod
    def save(cls, key: str, value: Optional[str]) -> bool:
        FirestoreClient.upsert_document(COLLECTION, str(key), {
            "key": key,
            "value": str(value or ""),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        return True
