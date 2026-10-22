"""Bodies of the e-mail template and WhatsApp text routes (Communications page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal

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
