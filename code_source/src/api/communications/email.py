"""E-mail templates, preview, sending configuration and sending (Gmail API or SMTP)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from api.communications.schemas import EmailDispatch, EmailStatus, EmailTemplate, EmailTemplateDeleted, EmailTemplates, EmailTemplateSaved, EmailTemplateUpdate
from api.responses import error, error_responses, internal_error
from infrastructure.mail.dispatch import EmailDispatchService
from infrastructure.security.secret_store import SecretStore

router = APIRouter()


@router.get("/api/email-templates", response_model=EmailTemplates, responses=error_responses(500))
def get_email_templates() -> EmailTemplates | JSONResponse:
    """Retourne la liste des modèles d'e-mails configurés."""
    try:
        rows = EmailDispatchService.list_templates()
        # Old rows may hold NULL columns
        templates = [EmailTemplate(**{field: str(row.get(field) or "") for field in EmailTemplate.model_fields}) for row in rows]
        return EmailTemplates(status="success", templates=templates)
    except Exception as e:
        return error(500, internal_error(e, "get_email_templates"))


def _same_name(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


@router.post("/api/email-templates", response_model=EmailTemplateSaved, responses=error_responses(400, 409, 500))
def save_email_template_api(data: EmailTemplateUpdate) -> EmailTemplateSaved | JSONResponse:
    """Crée ou met à jour un modèle d'e-mail dans la BDD SQLite (synchronisé avec Firestore)."""
    try:
        from infrastructure.sqlite.connection import DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME
        from infrastructure.sqlite.email_templates import EmailTemplateRepository
        if not data.name:
            return error(400, "Le nom du modèle est obligatoire.")
        if not data.subject:
            return error(400, "Le sujet du modèle est obligatoire.")
        if data.sender_email and ("@" not in data.sender_email or "." not in data.sender_email):
            return error(400, "L'adresse d'expédition doit être une adresse e-mail valide.")
        # A new name must not take another template's (the save would overwrite it, or fail on a rename)
        if not (data.old_name and _same_name(data.old_name, data.name)):
            others = (t["name"] for t in EmailTemplateRepository.get_email_templates() if t["name"] != data.old_name)
            if any(_same_name(other, data.name) for other in others):
                return error(409, f"Un modèle nommé « {data.name} » existe déjà.", "duplicate_name")

        ok = EmailTemplateRepository.save_email_template(
            name=data.name,
            subject=data.subject,
            body=data.body,
            sender_email=data.sender_email,
            sender_name=data.sender_name,
            old_name=data.old_name or None,
        )
        if not ok:
            return error(500, f"Impossible d'enregistrer le modèle '{data.name}'.")

        return EmailTemplateSaved(
            status="success",
            message=f"Modèle d'e-mail '{data.name}' enregistré avec succès.",
            template=EmailTemplate(
                name=data.name,
                subject=data.subject,
                body=data.body,
                sender_email=data.sender_email or DEFAULT_SENDER_EMAIL,
                sender_name=data.sender_name or DEFAULT_SENDER_NAME,
            ),
        )
    except Exception as e:
        return error(500, internal_error(e, "save_email_template_api"))


@router.delete("/api/email-templates/{template_name}", response_model=EmailTemplateDeleted, responses=error_responses(400, 404, 500))
def delete_email_template_api(template_name: str) -> EmailTemplateDeleted | JSONResponse:
    """Supprime un modèle d'e-mail par son nom."""
    try:
        from infrastructure.sqlite.email_templates import EmailTemplateRepository
        import urllib.parse
        clean_name = urllib.parse.unquote(template_name).strip()
        if not clean_name:
            return error(400, "Nom de modèle invalide.")

        ok = EmailTemplateRepository.delete_email_template(clean_name)
        if not ok:
            return error(404, f"Modèle '{clean_name}' introuvable ou déjà supprimé.")

        return EmailTemplateDeleted(status="success", message=f"Modèle '{clean_name}' supprimé avec succès.")
    except Exception as e:
        return error(500, internal_error(e, "delete_email_template_api"))


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


@router.get("/api/email-status", response_model=EmailStatus)
def get_email_status() -> EmailStatus:
    """Vérifie l'état de la configuration d'envoi d'e-mails (sans exposer de secrets)."""
    gmail_user = SecretStore.get_secret("GMAIL_USER_EMAIL")
    gmail_client_id = SecretStore.get_secret("GMAIL_CLIENT_ID")
    gmail_refresh = SecretStore.get_secret("GMAIL_REFRESH_TOKEN")

    smtp_host = SecretStore.get_secret("SMTP_HOST")
    smtp_user = SecretStore.get_secret("SMTP_USER")
    smtp_password = SecretStore.get_secret("SMTP_PASSWORD")

    use_oauth2 = bool(gmail_user and gmail_client_id and gmail_refresh)
    use_smtp = bool(smtp_host and smtp_user and smtp_password)

    return EmailStatus(
        status="success",
        configured=use_oauth2 or use_smtp,
        mode="gmail_oauth2" if use_oauth2 else ("smtp" if use_smtp else "none"),
        sender=(gmail_user if use_oauth2 else smtp_user if use_smtp else "") or "",
    )


@router.post("/api/send-email", response_model=EmailDispatch, responses=error_responses(403))
def send_email_api(request: Request, data: Dict[str, Any] = Body(...)) -> EmailDispatch | JSONResponse:  # Any: bodies of several pages
    """Déclenche l'envoi d'e-mails sécurisé via Gmail API ou SMTP avec injection de variables."""
    from infrastructure.security.api_auth import Role, has_role
    claims = getattr(request.state, "user", None)  # None: token check off (local desktop server)
    reason = EmailDispatchService.unauthorized_send_reason(
        data.get("recipients"), data.get("sender_email"),
        is_admin=claims is None or has_role(claims, Role.ADMIN))
    if reason:
        return error(403, reason)
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
        return EmailDispatch.model_validate(result)
    except Exception as e:
        return EmailDispatch(status="error", message=internal_error(e, "send_email_api"))
