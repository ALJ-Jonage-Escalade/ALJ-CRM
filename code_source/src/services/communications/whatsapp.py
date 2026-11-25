"""The WhatsApp invitation text of the Communications page, kept in the app settings (Firestore)."""

from __future__ import annotations

from domain.errors import InvalidRequest
from infrastructure.firestore.app_settings import WHATSAPP_TEMPLATE, AppSettingsRepository


def get_template() -> str:
    return AppSettingsRepository.get(WHATSAPP_TEMPLATE) or ""


def save_template(text: str) -> None:
    if not text:
        raise InvalidRequest("Le texte WhatsApp ne peut pas être vide.")
    AppSettingsRepository.save(WHATSAPP_TEMPLATE, text)
