"""WhatsApp invitation text."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.communications.schemas import WhatsappTemplate, WhatsappTemplateSaved, WhatsappTemplateUpdate
from api.responses import error, error_responses

router = APIRouter()


@router.get("/api/whatsapp-template", response_model=WhatsappTemplate, responses=error_responses(500))
def get_whatsapp_template_api() -> WhatsappTemplate | JSONResponse:
    """Retourne le texte d'invitation WhatsApp mémorisé."""
    from infrastructure.firestore.app_settings import WHATSAPP_TEMPLATE, AppSettingsRepository
    text = AppSettingsRepository.get(WHATSAPP_TEMPLATE)
    return WhatsappTemplate(status="success", template=text or "")


@router.post("/api/whatsapp-template", response_model=WhatsappTemplateSaved, responses=error_responses(400, 500))
def save_whatsapp_template_api(data: WhatsappTemplateUpdate) -> WhatsappTemplateSaved | JSONResponse:
    """Enregistre le texte d'invitation WhatsApp."""
    from infrastructure.firestore.app_settings import WHATSAPP_TEMPLATE, AppSettingsRepository
    if not data.template:
        return error(400, "Le texte WhatsApp ne peut pas être vide.")
    ok = AppSettingsRepository.save(WHATSAPP_TEMPLATE, data.template)
    if not ok:
        return error(500, "Impossible d'enregistrer le texte WhatsApp.")
    return WhatsappTemplateSaved(status="success", message="Texte WhatsApp enregistré avec succès.", template=data.template)
