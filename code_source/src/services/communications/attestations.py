"""Payment certificates sent by e-mail (admin): the PDF generated in memory, the e-mail, the sent date on the
purchase and the e-mail log entry."""

from __future__ import annotations

import datetime
import logging
from typing import Optional, TypedDict

from domain.club_emails import CLUB_CONTACT_EMAIL, DEFAULT_SENDER_NAME
from domain.email_personalization import apply_template_variables, personalized_html, template_recipient
from domain.errors import InvalidRequest, UpstreamUnavailable
from exports.attestation import attestation_error, build_attestation, get_safe_pdf_filename, render_attestation_pdf
from infrastructure.mail.html_body import build_email_html, build_signature_plain, get_inline_images
from infrastructure.mail.sender import EmailSender, MailError
from infrastructure.sqlite.members import MemberRepository
from services.communications.email_dispatch import EmailDispatchService
from services.communications.email_log import SEND_FAILED, logged_recipient, record_send
from services.communications.senders import resolve_sender
from services.documents import Doc
from services.members.members import MemberService

logger = logging.getLogger("alj")

DEFAULT_TEMPLATE = "Attestation échéance"
DEFAULT_SUBJECT = "Attestation de paiement et d'échéance - Amicale Laïque de Jonage"
DEFAULT_BODY = (
    "Bonjour {first_name},\n\n"
    "Nous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\n"
    "Sportivement,\n"
    "L'équipe ALJ Escalade"
)


class AttestationEmail(TypedDict):
    message: str
    email_sent_date: Optional[str]  # None when the e-mail went out but the date could not be saved
    filename: str


def attestation_filename(member: Doc) -> str:
    return get_safe_pdf_filename(member.get("last_name") or "ADHERENT", member.get("first_name") or "", member.get("order_ref"))


def attestation_member(season: Optional[str], purchase_id: int) -> Doc:
    """The member of this purchase (NotFound), when a certificate can be made for it (InvalidRequest otherwise)."""
    member = MemberService.find_member(season, purchase_id)
    problem = attestation_error(member)
    if problem:
        raise InvalidRequest(problem)
    return member


def attestation_pdf(member: Doc) -> bytes:
    return render_attestation_pdf(build_attestation(member, season=member.get("season_name"), club_email=CLUB_CONTACT_EMAIL))


def send_attestation(season: Optional[str], purchase_id: int, to_email: str, author: str, template_name: str = "",
                     subject: str = "", body: str = "", add_signature: bool = True) -> AttestationEmail:
    """Sends the member's certificate to `to_email` (an empty subject or body falls back to the template), then
    records the sent date on the purchase. Raises InvalidRequest, NotFound, Forbidden (a sender that is not the account nor one of its aliases) and
    UpstreamUnavailable (the e-mail did not leave)."""
    if not to_email or "@" not in to_email:
        raise InvalidRequest("Adresse e-mail du destinataire invalide ou manquante.")
    member = attestation_member(season, purchase_id)
    pdf_bytes = attestation_pdf(member)
    filename = attestation_filename(member)

    template = EmailDispatchService.get_template_by_name(template_name or DEFAULT_TEMPLATE)
    raw_subject = subject or (template.get("subject") if template else None) or DEFAULT_SUBJECT
    raw_body = body or (template.get("body") if template else None) or DEFAULT_BODY
    recipient = template_recipient(member)
    final_subject = apply_template_variables(raw_subject, recipient)
    final_body = apply_template_variables(raw_body, recipient)

    sender_email = resolve_sender(template.get("sender_email") if template else None)
    sender_name = (template.get("sender_name") if template else None) or DEFAULT_SENDER_NAME

    # HTML built from the template, then personalised with escaped values
    html_body = personalized_html(
        raw_body, recipient, lambda text: build_email_html(text, add_signature=True, image_src_mode="cid")
    ) if add_signature else None
    plain_body = final_body + ("\n\n" + build_signature_plain() if add_signature else "")

    member_id = member.get("user_id")
    name = f"{member.get('first_name') or ''} {member.get('last_name') or ''}"
    used_template = template["name"] if template else ""
    try:
        EmailSender.send_email(
            to_email=to_email,
            subject=final_subject,
            body=plain_body,
            html_body=html_body,
            attachment_bytes=pdf_bytes,
            attachment_filename=filename,
            inline_images=get_inline_images() if add_signature else [],
            from_email=sender_email,
            from_name=sender_name,
        )
    except MailError as e:
        logger.exception("Attestation: e-mail to %s not sent", to_email)
        record_send("attestation", author, [logged_recipient(to_email, name, member_id, SEND_FAILED)], final_subject, used_template)
        raise UpstreamUnavailable("Échec d'envoi de l'e-mail (détails dans les journaux).") from e
    log_notice = record_send("attestation", author, [logged_recipient(to_email, name, member_id)], final_subject, used_template)

    # Date the certificate was sent, in SQLite (replicated to Firestore after the request, server.py).
    # The e-mail is already gone: a failure here must not answer an error (the office would send it again)
    now_str = datetime.datetime.now().strftime("%d/%m/%Y")
    try:
        recorded = MemberRepository.update_email_sent_date(
            order_ref=str(member.get("order_ref") or "").strip(),
            last_name=str(member.get("last_name") or "").strip(),
            first_name=str(member.get("first_name") or "").strip(),
            date_str=now_str,
            purchase_id=int(member["purchase_id"]),
        )
    except Exception:  # the e-mail was sent: report the unsaved date instead of failing the request
        logger.exception("Attestation: sent date not recorded in SQLite")
        recorded = False
    else:
        if not recorded:
            logger.error("Attestation: no purchase matched to record the sent date (purchase #%s)", member.get("purchase_id"))

    message = f"Attestation envoyée avec succès à {to_email}."
    if not recorded:
        message += " La date d'envoi n'a pas pu être enregistrée sur la fiche."
    if log_notice:
        message += f" {log_notice}"
    return AttestationEmail(message=message, email_sent_date=now_str if recorded else None, filename=filename)
