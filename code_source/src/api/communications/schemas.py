"""Bodies of the e-mail template and WhatsApp text routes (Communications page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

from api.request_body import RequestBody
from domain.email_variables import TemplateKind, VariableKey


class EmailTemplate(BaseModel):
    name: str
    subject: str
    body: str
    sender_email: str
    sender_name: str


class EmailTemplates(BaseModel):
    """default_sender_*: used by the server when a template's sender is empty. club_contact_email: shown in the e-mail signature."""
    status: Literal["success"]
    templates: List[EmailTemplate]
    default_sender_email: str
    default_sender_name: str
    sender_suggestions: List[str]
    club_contact_email: str


class EmailVariable(BaseModel):
    """A template variable: `key` is stored in the templates, `label` is what users read and type ({Prénom});
    `aliases`: former spellings still accepted in saved templates."""
    key: VariableKey
    label: str
    kinds: List[TemplateKind]
    demo: str
    aliases: List[str]


class EmailVariables(BaseModel):
    status: Literal["success"]
    variables: List[EmailVariable]


class EmailTemplateUpdate(RequestBody):
    """old_name: the template's current name, to rename it; empty for a new template.
    An empty sender falls back to the club's default address and name."""
    name: str = ""
    old_name: str = ""
    subject: str = ""
    body: str = ""
    sender_email: str = ""
    sender_name: str = ""


class EmailTemplateSaved(BaseModel):
    status: Literal["success"]
    message: str
    template: EmailTemplate


class EmailTemplateDeleted(BaseModel):
    status: Literal["success"]
    message: str


class WhatsappTemplate(BaseModel):
    status: Literal["success"]
    template: str


class WhatsappTemplateUpdate(RequestBody):
    template: str = ""


class WhatsappTemplateSaved(BaseModel):
    status: Literal["success"]
    message: str
    template: str


class AttestationRequest(RequestBody):
    """The membership (purchase) the certificate is about; the server reads its amount, payer and status itself.
    season: the active season when empty."""
    purchase_id: int
    season: str = ""


class AttestationSend(AttestationRequest):
    """The e-mail sent with the certificate; an empty subject or body falls back to the template."""
    to_email: str
    template_name: str = ""
    subject: str = ""
    body: str = ""
    add_signature: bool = True


class AttestationSent(BaseModel):
    status: Literal["success"]
    message: str
    email_sent_date: Optional[str]  # None when the e-mail went out but the date could not be saved
    filename: str


class EmailSendDetail(BaseModel):
    """Outcome for one recipient."""
    id: Optional[Union[int, str]] = None
    name: str = ""
    email: Optional[str] = None
    status: Literal["sent", "error"]
    error: Optional[str] = None


class EmailStatus(BaseModel):
    """Sending configuration of /api/email-status (no secret: the sender address only).
    mode: Gmail API (OAuth2) first, else SMTP, else "none" (configured is then false)."""
    status: Literal["success"]
    configured: bool
    mode: Literal["gmail_oauth2", "smtp", "none"]
    sender: str


class EmailRecipient(RequestBody):
    """A recipient given by the page; its fields are also the template variables ({first_name}, {tarif}…).
    amount: the membership amount, in euros."""
    id: Optional[int] = None
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    num_licence: str = ""
    tarif: str = ""
    season: str = ""
    amount: Optional[float] = None


class EmailSendRequest(RequestBody):
    """template_name: a saved template, whose subject, body and sender fill what is left empty here.
    recipient_ids: members of the cache; recipients: people given by the page (both may be used)."""
    template_name: str = ""
    subject: str = ""
    body: str = ""
    recipient_ids: List[int] = []
    recipients: List[EmailRecipient] = []
    competition_id: Optional[int] = None
    sender_email: str = ""
    sender_name: str = ""
    add_signature: bool = True


class EmailDispatch(BaseModel):
    """Outcome of /api/send-email when at least one e-mail left: status "partial" when some recipients failed (see
    details). A refused request is a 400, and a sending where every e-mail failed a 502."""
    status: Literal["success", "partial"]
    message: str = ""
    sent_count: int = 0
    errors_count: int = 0
    total_recipients: int = 0
    details: List[EmailSendDetail] = []
    log_notice: Optional[str] = Field(None, description="Set when the e-mails left but the send is missing from the e-mail log")
