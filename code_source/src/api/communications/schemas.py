"""Bodies of the e-mail template and WhatsApp text routes (Communications page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel

from api.request_body import RequestBody


class EmailTemplate(BaseModel):
    name: str
    subject: str
    body: str
    sender_email: str
    sender_name: str


class EmailTemplates(BaseModel):
    status: Literal["success"]
    templates: List[EmailTemplate]


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
    email_sent_date: str
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


class EmailDispatch(BaseModel):
    """Outcome of /api/send-email. A refused request (empty subject, no valid recipient) or a failed sending is
    answered with HTTP 200 and status "error": the caller checks `status`, not the HTTP code."""
    status: Literal["success", "partial", "error"]
    message: str = ""
    sent_count: int = 0
    errors_count: int = 0
    total_recipients: int = 0
    details: List[EmailSendDetail] = []
