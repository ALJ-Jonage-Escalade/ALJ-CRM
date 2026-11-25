"""E-mail templates, sending configuration and sending (Gmail API or SMTP)."""

from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.communications.schemas import (
    EmailDispatch, EmailSendRequest, EmailStatus, EmailTemplate,
    EmailTemplateDeleted, EmailTemplates, EmailTemplateSaved, EmailTemplateUpdate, EmailVariable, EmailVariables,
)
from api.auth.me import author_of
from api.responses import error, error_responses
from services.communications.email_dispatch import EmailDispatchService, OutgoingEmail
from services.communications.email_templates import delete_template, list_templates, save_template
from domain.email_variables import VARIABLES, aliases_of
from domain.club_emails import CLUB_CONTACT_EMAIL, DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME, SENDER_SUGGESTIONS
from infrastructure.security.secret_store import SecretStore
from infrastructure.security.api_auth import Role, has_role

router = APIRouter()


@router.get("/api/email-templates", response_model=EmailTemplates, responses=error_responses(500))
def get_email_templates() -> EmailTemplates:
    """Retourne la liste des modèles d'e-mails configurés."""
    templates = [EmailTemplate(**template) for template in list_templates()]
    return EmailTemplates(
        status="success",
        templates=templates,
        default_sender_email=DEFAULT_SENDER_EMAIL,
        default_sender_name=DEFAULT_SENDER_NAME,
        sender_suggestions=list(SENDER_SUGGESTIONS),
        club_contact_email=CLUB_CONTACT_EMAIL,
    )


@router.get("/api/email-templates/variables", response_model=EmailVariables)
def get_email_variables() -> EmailVariables:
    """The variables templates may use, with their French label, kinds, demo value and former spellings."""
    return EmailVariables(status="success", variables=[
        EmailVariable(key=v.key, label=v.label, kinds=list(v.kinds), demo=v.demo, aliases=aliases_of(v.key)) for v in VARIABLES
    ])


@router.post("/api/email-templates", response_model=EmailTemplateSaved, responses=error_responses(400, 409, 500))
def save_email_template_api(data: EmailTemplateUpdate) -> EmailTemplateSaved:
    """Crée ou met à jour un modèle d'e-mail dans la BDD SQLite (synchronisé avec Firestore)."""
    saved = save_template(name=data.name, subject=data.subject, body=data.body, sender_email=data.sender_email,
                          sender_name=data.sender_name, old_name=data.old_name, kind=data.kind,
                          is_default=data.is_default)
    return EmailTemplateSaved(status="success", message=f"Modèle d'e-mail '{data.name}' enregistré avec succès.",
                              template=EmailTemplate(**saved))


@router.delete("/api/email-templates/{template_name}", response_model=EmailTemplateDeleted, responses=error_responses(400, 404, 500))
def delete_email_template_api(template_name: str) -> EmailTemplateDeleted:
    """Supprime un modèle d'e-mail par son nom."""
    deleted_name = delete_template(urllib.parse.unquote(template_name))
    return EmailTemplateDeleted(status="success", message=f"Modèle '{deleted_name}' supprimé avec succès.")



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


@router.post("/api/send-email", response_model=EmailDispatch, responses=error_responses(400, 403, 500, 502))
def send_email_api(request: Request, data: EmailSendRequest) -> EmailDispatch | JSONResponse:
    """Envoie un e-mail personnalisé à chaque destinataire (Gmail API ou SMTP), avec les variables remplacées.
    400: nothing to send (empty subject or body, no valid recipient); 502: every e-mail failed."""
    claims = getattr(request.state, "user", None)  # None: token check off (local dev server)
    recipients = [recipient.model_dump() for recipient in data.recipients]
    reason = EmailDispatchService.unauthorized_send_reason(
        recipients, data.sender_email or None, is_admin=claims is None or has_role(claims, Role.ADMIN))
    if reason:
        return error(403, reason)
    message = OutgoingEmail(template_name=data.template_name, subject=data.subject, body=data.body,
                            sender_email=data.sender_email, sender_name=data.sender_name, add_signature=data.add_signature)
    result = EmailDispatchService.dispatch_emails(message, recipient_ids=data.recipient_ids, recipients=recipients,
                                                  competition_id=data.competition_id, author=author_of(request))
    return EmailDispatch.model_validate(result)
