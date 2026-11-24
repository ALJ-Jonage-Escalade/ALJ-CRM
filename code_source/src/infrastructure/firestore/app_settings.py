"""Application settings (key/value) in the Firestore `app_settings` collection.

Single store for every setting: HelloAsso annual campaign, WhatsApp invitation text,
results batch notification e-mail and status, webhook notification marks…
"""

from __future__ import annotations

import datetime
from typing import Optional

from infrastructure.firestore.client import FirestoreClient

COLLECTION = "app_settings"

WHATSAPP_TEMPLATE = "whatsapp_template"
# Active HelloAsso campaigns, saved as "FormType:slug" (Paramètres › Campagne HelloAsso)
HELLOASSO_MEMBERSHIP_CAMPAIGN = "HELLOASSO_MEMBERSHIP_CAMPAIGN"
HELLOASSO_COMPETITION_CAMPAIGN = "HELLOASSO_ANNUAL_CAMPAIGN"


class AppSettingsRepository:
    """Lecture / écriture des réglages applicatifs (toutes les méthodes sont des classmethods)."""

    @classmethod
    def get(cls, key: str, default: Optional[str] = "") -> Optional[str]:
        """Value of the setting, or `default` when it is missing or blank."""
        doc = FirestoreClient.get_document(COLLECTION, str(key))
        value = doc.get("value") if doc is not None else None
        if value is None or not str(value).strip():
            return default
        return str(value)

    @classmethod
    def save(cls, key: str, value: Optional[str]) -> None:
        """Writes the setting; a Firestore failure raises FirestoreError."""
        FirestoreClient.upsert_document(COLLECTION, str(key), {
            "key": key,
            "value": str(value or ""),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
