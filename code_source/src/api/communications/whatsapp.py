"""WhatsApp invitation text."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from api.responses import internal_error

router = APIRouter()


@router.get("/api/whatsapp-template")
def get_whatsapp_template_api():
    """Retourne le texte d'invitation WhatsApp mémorisé."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        text = SqliteRepository.get_whatsapp_template()
        return {"status": "success", "template": text or ""}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "get_whatsapp_template_api")})


@router.post("/api/whatsapp-template")
def save_whatsapp_template_api(data: Dict[str, Any] = Body(...)):
    """Enregistre le texte d'invitation WhatsApp."""
    try:
        from infrastructure.sqlite.repository import SqliteRepository
        text = str(data.get("template") or "").strip()
        ok = SqliteRepository.save_whatsapp_template(text)
        if not ok:
            return JSONResponse(status_code=500, content={"status": "error", "message": "Impossible d'enregistrer le texte WhatsApp."})
        return {"status": "success", "message": "Texte WhatsApp enregistré avec succès.", "template": text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "save_whatsapp_template_api")})
