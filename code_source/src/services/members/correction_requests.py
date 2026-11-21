"""Correction requests to the families from the HelloAsso membership import (plans/helloasso-import-data-checks.md).

One e-mail per HelloAsso order of the chosen registrations, to the payer, the primary club e-mail in copy when valid
and different, the answers going to the template's sender (a club address). The text is the template « Adhésion :
informations à corriger » (editable in Communications › Modèles); its {problemes} variable lists the problems still
present. Each send action is recorded in the e-mail log with its orders and registrations.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence, TypedDict

from domain.club_emails import DEFAULT_SENDER_EMAIL
from domain.email_log import LoggedRecipient
from domain.errors import InvalidRequest, UpstreamUnavailable
from domain.members.correction_request import CORRECTION_REQUEST_TEMPLATE, PROBLEMS_VARIABLE, CorrectionRequest, correction_requests
from infrastructure.mail.html_body import get_inline_images
from infrastructure.mail.sender import EmailSender, MailError
from infrastructure.sqlite.connection import CORRECTION_REQUEST_EMAIL_TEMPLATE
from services.communications.email_dispatch import EmailDispatchService, RenderedEmail, render_email
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send
from services.members.helloasso_import import MembershipImportService

logger = logging.getLogger("alj")


class CorrectionEmail(TypedDict):
    to: str
    cc: List[str]
    subject: str
    body: str  # plain text


class RequestOutcome(TypedDict):
    sent: int  # e-mails that left
    failed: int
    log_notice: Optional[str]  # the send could not be recorded in the e-mail log


class _Template(TypedDict):
    subject: str
    body: str
    sender_email: str
    sender_name: str


def _template() -> _Template:
    """The template as the club edited it; the one shipped with the app when it was deleted."""
    _name, subject, body, sender_email, sender_name = CORRECTION_REQUEST_EMAIL_TEMPLATE
    saved = EmailDispatchService.get_template_by_name(CORRECTION_REQUEST_TEMPLATE) or {}
    return _Template(subject=saved.get("subject") or subject, body=saved.get("body") or body,
                     sender_email=saved.get("sender_email") or sender_email or DEFAULT_SENDER_EMAIL,
                     sender_name=saved.get("sender_name") or sender_name)


def _requests(item_ids: Sequence[int], chosen_campaign: Optional[str]) -> list[CorrectionRequest]:
    """The requests of the chosen registrations, on the preview recomputed now. InvalidRequest when none has a problem."""
    chosen = set(item_ids)
    plan = MembershipImportService.preview(chosen_campaign)
    requests = correction_requests(entry for entry in plan.entries if entry.item_id in chosen)
    if not requests:
        raise InvalidRequest("Aucune des inscriptions choisies n'a d'information à corriger.", "nothing_to_request")
    return requests


def _render(request: CorrectionRequest, template: _Template) -> RenderedEmail:
    payer = {"first_name": request.payer_first_name, "last_name": request.payer_last_name}
    return render_email(template["subject"], template["body"], payer, {}, add_signature=True,
                        extra_variables={PROBLEMS_VARIABLE: request.problems})


def example(item_ids: Sequence[int], chosen_campaign: Optional[str] = None) -> CorrectionEmail:
    """The e-mail of the first order, as it would be sent. Sends nothing."""
    request = _requests(item_ids, chosen_campaign)[0]
    rendered = _render(request, _template())
    return CorrectionEmail(to=request.payer_email, cc=list(request.cc), subject=rendered["subject"], body=rendered["body_plain"])


def send(item_ids: Sequence[int], author: str, chosen_campaign: Optional[str] = None) -> RequestOutcome:
    """Sends one e-mail per order, then records the send. A failed e-mail does not stop the others;
    UpstreamUnavailable when none left (recorded too)."""
    requests = _requests(item_ids, chosen_campaign)
    template = _template()
    logged: List[LoggedRecipient] = []
    subjects: List[str] = []
    sent = 0
    for request in requests:
        rendered = _render(request, template)
        subjects.append(rendered["subject"])
        payer_name = f"{request.payer_first_name} {request.payer_last_name}"
        try:
            EmailSender.send_email(to_email=request.payer_email, subject=rendered["subject"], body=rendered["body_plain"],
                                   html_body=rendered["body_html"], inline_images=get_inline_images(),
                                   from_email=template["sender_email"], from_name=template["sender_name"], cc=list(request.cc),
                                   reply_to=template["sender_email"])
        except MailError as e:  # this order only: the others are still sent
            logger.warning("Demande de correction de la commande %s non envoyée : %s", request.order_ref, e)
            logged.append(logged_recipient(request.payer_email, payer_name, error=SEND_FAILED))
            continue
        sent += 1
        logged.append(logged_recipient(request.payer_email, payer_name))
        logged.extend(logged_recipient(address) for address in request.cc)
    log_notice = record_send("correction_request", author, logged, subjects[0], template=CORRECTION_REQUEST_TEMPLATE,
                             helloasso_order_refs=[request.order_ref for request in requests],
                             helloasso_item_ids=[item_id for request in requests for item_id in request.item_ids])
    if not sent:
        raise UpstreamUnavailable(f"Aucune demande de correction n'est partie : {SEND_FAILED}")
    return RequestOutcome(sent=sent, failed=len(requests) - sent, log_notice=log_notice)
