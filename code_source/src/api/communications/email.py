"""E-mail templates, sending configuration and sending (Gmail API or SMTP)."""

from __future__ import annotations


from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from api.communications.schemas import (
    EmailDispatch, EmailSendRequest, EmailStatus, EmailTemplate,
    EmailTemplateDeleted, EmailTemplates, EmailTemplateSaved, EmailTemplateUpdate, EmailVariable, EmailVariables,
)
from api.auth.me import author_of
from api.responses import error, error_responses
from services.communications.email_dispatch import EmailDispatchService
from services.communications.email_templates import list_templates, save_template
from services.communications.senders import allowed_senders
from domain.email_variables import VARIABLES, aliases_of
from domain.club_emails import CLUB_CONTACT_EMAIL, DEFAULT_SENDER_NAME
from infrastructure.security.secret_store import SecretStore
from infrastructure.security.api_auth import Role, has_role
from infrastructure.sqlite.email_templates import EmailTemplateRepository

router = APIRouter()


@router.get("/api/email-templates", response_model=EmailTemplates, responses=error_responses(500))
def get_email_templates() -> EmailTemplates | JSONResponse:
    """Retourne la liste des modèles d'e-mails configurés."""
    templates = [EmailTemplate(**template) for template in list_templates()]
    senders = allowed_senders()
    return EmailTemplates(
        status="success",
        templates=templates,
        default_sender_email=senders["account"],
        default_sender_name=DEFAULT_SENDER_NAME,
        sender_aliases=senders["aliases"],
        sender_aliases_error=senders["error"],
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
def delete_email_template_api(template_name: str) -> EmailTemplateDeleted | JSONResponse:
    """Supprime un modèle d'e-mail par son nom."""
    import urllib.parse
    clean_name = urllib.parse.unquote(template_name).strip()
    if not clean_name:
        return error(400, "Nom de modèle invalide.")

    if not EmailTemplateRepository.delete_email_template(clean_name):
        return error(404, f"Modèle '{clean_name}' introuvable ou déjà supprimé.")

    return EmailTemplateDeleted(status="success", message=f"Modèle '{clean_name}' supprimé avec succès.")



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
    400: nothing to send (empty subject or body, no valid recipient), or both a template and a sender; 403: a coach
    writing to an unknown address, or a sender that is not the account nor one of its aliases; 502: every e-mail failed."""
    if data.template_name and data.sender_email:
        return error(400, "Un e-mail part soit de l'expéditeur de son modèle, soit de l'adresse choisie, pas des deux.")
    claims = getattr(request.state, "user", None)  # None: token check off (local dev server)
    recipients = [recipient.model_dump() for recipient in data.recipients]
    reason = EmailDispatchService.unauthorized_send_reason(recipients, is_admin=claims is None or has_role(claims, Role.ADMIN))
    if reason:
        return error(403, reason)
    result = EmailDispatchService.dispatch_emails(
        template_name=data.template_name or None,
        subject=data.subject,
        body=data.body,
        recipient_ids=data.recipient_ids,
        recipients=recipients,
        competition_id=data.competition_id,
        sender_email=data.sender_email or None,
        sender_name=data.sender_name or None,
        add_signature=data.add_signature,
        author=author_of(request),
    )
    return EmailDispatch.model_validate(result)
