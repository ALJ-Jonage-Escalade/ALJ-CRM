"""E-mail templates, preview, sending configuration and sending (Gmail API or SMTP)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from api.responses import internal_error
from infrastructure.mail.dispatch import EmailDispatchService
from infrastructure.security.secret_store import SecretStore

router = APIRouter()


@router.get("/api/email-templates")
def get_email_templates():
    """Retourne la liste des modèles d'e-mails configurés."""
    try:
        return {"status": "success", "templates": EmailDispatchService.list_templates()}
    except Exception as e:
        return {"status": "error", "message": internal_error(e, "get_email_templates")}


@router.post("/api/email-templates")
def save_email_template_api(data: Dict[str, Any] = Body(...)):
    """Crée ou met à jour un modèle d'e-mail dans la BDD SQLite (synchronisé avec Firestore)."""
    try:
        from infrastructure.sqlite.email_templates import EmailTemplateRepository
        name = str(data.get("name") or "").strip()
        old_name = str(data.get("old_name") or "").strip() or None
        subject = str(data.get("subject") or "").strip()
        body = str(data.get("body") or "").strip()
        sender_email = str(data.get("sender_email") or "").strip()
        sender_name = str(data.get("sender_name") or "").strip()

        if not name:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Le nom du modèle est obligatoire."})
        if not subject:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Le sujet du modèle est obligatoire."})

        ok = EmailTemplateRepository.save_email_template(
            name=name,
            subject=subject,
            body=body,
            sender_email=sender_email,
            sender_name=sender_name,
            old_name=old_name
        )
        if not ok:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"Impossible d'enregistrer le modèle '{name}'."})

        return {
            "status": "success",
            "message": f"Modèle d'e-mail '{name}' enregistré avec succès.",
            "template": {
                "name": name,
                "subject": subject,
                "body": body,
                "sender_email": sender_email,
                "sender_name": sender_name
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "save_email_template_api")})


@router.delete("/api/email-templates/{template_name}")
def delete_email_template_api(template_name: str):
    """Supprime un modèle d'e-mail par son nom."""
    try:
        from infrastructure.sqlite.email_templates import EmailTemplateRepository
        import urllib.parse
        clean_name = urllib.parse.unquote(template_name).strip()
        if not clean_name:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Nom de modèle invalide."})

        ok = EmailTemplateRepository.delete_email_template(clean_name)
        if not ok:
            return JSONResponse(status_code=404, content={"status": "error", "message": f"Modèle '{clean_name}' introuvable ou déjà supprimé."})

        return {"status": "success", "message": f"Modèle '{clean_name}' supprimé avec succès."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "delete_email_template_api")})


@router.post("/api/preview-email")
def preview_email(data: Dict[str, Any] = Body(...)):
    """Génère un aperçu fidèle d'un e-mail personnalisé pour un destinataire et une compétition."""
    try:
        preview_data = EmailDispatchService.preview(
            template_name=data.get("template_name"),
            subject=data.get("subject"),
            body=data.get("body"),
            recipient=data.get("recipient"),
            competition_id=data.get("competition_id"),
            add_signature=data.get("add_signature", True)
        )
        return {"status": "success", "preview": preview_data}
    except Exception as e:
        return {"status": "error", "message": internal_error(e, "preview_email")}


@router.get("/api/email-status")
def get_email_status():
    """Vérifie l'état de la configuration d'envoi d'e-mails (sans exposer de secrets)."""
    gmail_user = SecretStore.get_secret("GMAIL_USER_EMAIL")
    gmail_client_id = SecretStore.get_secret("GMAIL_CLIENT_ID")
    gmail_refresh = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")

    smtp_host = SecretStore.get_secret("SMTP_HOST")
    smtp_user = SecretStore.get_secret("SMTP_USER")
    smtp_password = SecretStore.get_secret("SMTP_PASSWORD")

    use_oauth2 = bool(gmail_user and gmail_client_id and gmail_refresh)
    use_smtp = bool(smtp_host and smtp_user and smtp_password)

    return {
        "status": "success",
        "configured": use_oauth2 or use_smtp,
        "mode": "gmail_oauth2" if use_oauth2 else ("smtp" if use_smtp else "none"),
        "sender": gmail_user if use_oauth2 else (smtp_user if use_smtp else ""),
    }


@router.post("/api/send-email")
def send_email_api(request: Request, data: Dict[str, Any] = Body(...)):
    """Déclenche l'envoi d'e-mails sécurisé via Gmail API ou SMTP avec injection de variables."""
    from infrastructure.security.api_auth import Role, has_role
    claims = getattr(request.state, "user", None)  # None: token check off (local desktop server)
    reason = EmailDispatchService.unauthorized_send_reason(
        data.get("recipients"), data.get("sender_email"),
        is_admin=claims is None or has_role(claims, Role.ADMIN))
    if reason:
        return JSONResponse(status_code=403, content={"status": "error", "message": reason})
    try:
        result = EmailDispatchService.dispatch_emails(
            template_name=data.get("template_name"),
            subject=data.get("subject"),
            body=data.get("body"),
            recipient_ids=data.get("recipient_ids"),
            recipients=data.get("recipients"),
            competition_id=data.get("competition_id"),
            sender_email=data.get("sender_email"),
            sender_name=data.get("sender_name"),
            add_signature=data.get("add_signature", True)
        )
        return result
    except Exception as e:
        return {"status": "error", "message": internal_error(e, "send_email_api")}
