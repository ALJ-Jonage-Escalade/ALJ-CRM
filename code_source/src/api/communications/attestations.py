"""Payment certificates as PDF, one member at a time (admin): generated in memory, never stored."""

from __future__ import annotations

import datetime
import logging
import unicodedata
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from api.communications.schemas import AttestationRequest, AttestationSend, AttestationSent
from api.responses import error, error_responses, internal_error
from infrastructure.mail.senders import DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME
from services.documents import Doc
from services.members.members import MemberService

router = APIRouter()
logger = logging.getLogger("alj")

_PDF = {200: {"content": {"application/pdf": {}}, "description": "The certificate (PDF)"}}


def _filename(member: Doc) -> str:
    from domain.attestation.document import get_safe_pdf_filename
    return get_safe_pdf_filename(member.get("last_name") or "ADHERENT", member.get("first_name") or "", member.get("order_ref"))


def _content_disposition(filename: str) -> str:
    """Header of the PDF: HTTP headers are Latin-1, so an ASCII name plus the UTF-8 one (RFC 6266) for accented names."""
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


@router.post("/api/attestations/preview", response_class=Response, responses={**_PDF, **error_responses(400, 404, 500)})
def preview_attestation_api(data: AttestationRequest) -> Response:
    """Génère l'aperçu PDF d'une attestation de paiement (retourne application/pdf)."""
    member = MemberService.find_member(data.season, data.purchase_id)  # 404: service error handler
    from domain.attestation.document import attestation_error, build_attestation, render_attestation_pdf
    problem = attestation_error(member)
    if problem:
        return error(400, problem)
    try:
        pdf_bytes = render_attestation_pdf(build_attestation(member, season=member.get("season_name")))
    except Exception as e:
        return error(500, internal_error(e, "preview_attestation_api"))
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": _content_disposition(_filename(member))})


@router.post("/api/attestations/send", response_model=AttestationSent, responses=error_responses(400, 403, 404, 500))
def send_attestation_api(data: AttestationSend) -> AttestationSent | JSONResponse:
    """Génère une attestation PDF en mémoire, l'envoie par e-mail et met à jour la date d'envoi."""
    to_email = data.to_email
    if not to_email or "@" not in to_email:
        return error(400, "Adresse e-mail du destinataire invalide ou manquante.")
    member = MemberService.find_member(data.season, data.purchase_id)
    from domain.attestation.document import attestation_error
    problem = attestation_error(member)
    if problem:
        return error(400, problem)
    try:
        return _send(member, data)
    except Exception as e:
        return error(500, internal_error(e, "send_attestation_api"))


def _send(member: Doc, data: AttestationSend) -> AttestationSent | JSONResponse:
    from domain.attestation.document import build_attestation, render_attestation_pdf
    from domain.utils import apply_template_variables
    from infrastructure.mail.dispatch import EmailDispatchService
    from infrastructure.mail.html_body import build_email_html, build_signature_plain, get_inline_images
    from infrastructure.mail.repository import EmailRepository

    pdf_bytes = render_attestation_pdf(build_attestation(member, season=member.get("season_name")))
    filename_pdf = _filename(member)

    tmpl = EmailDispatchService.get_template_by_name(data.template_name or "Attestation échéance")
    raw_subject = data.subject or (tmpl.get("subject") if tmpl else None) or "Attestation de paiement et d'échéance - Amicale Laïque de Jonage"
    raw_body = data.body or (tmpl.get("body") if tmpl else None) or (
        "Bonjour {first_name},\n\n"
        "Nous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\n"
        "Sportivement,\n"
        "L'équipe ALJ Escalade"
    )
    subject = apply_template_variables(raw_subject, member)
    body = apply_template_variables(raw_body, member)

    sender_email = (tmpl.get("sender_email") if tmpl else None) or DEFAULT_SENDER_EMAIL
    if not EmailDispatchService.is_allowed_sender(sender_email):
        return error(403, f"Adresse d'expédition non autorisée : {sender_email}")
    sender_name = (tmpl.get("sender_name") if tmpl else None) or DEFAULT_SENDER_NAME

    # HTML built from the template, then personalised with escaped values
    html_body = apply_template_variables(
        build_email_html(raw_body, add_signature=True, image_src_mode="cid"), member, escape_html=True
    ) if data.add_signature else None
    plain_body = body + ("\n\n" + build_signature_plain() if data.add_signature else "")
    inline_images = get_inline_images() if data.add_signature else []

    ok = EmailRepository.send_email(
        to_email=data.to_email,
        subject=subject,
        body=plain_body,
        html_body=html_body,
        attachment_bytes=pdf_bytes,
        attachment_filename=filename_pdf,
        inline_images=inline_images,
        from_email=sender_email,
        from_name=sender_name
    )
    if not ok:
        return error(500, "Échec d'envoi de l'e-mail.")

    # Date the certificate was sent, in SQLite (replicated to Firestore after the request, server.py)
    now_str = datetime.datetime.now().strftime("%d/%m/%Y")
    try:
        from infrastructure.sqlite.members import MemberRepository
        MemberRepository.update_email_sent_date(
            order_ref=str(member.get("order_ref") or "").strip(),
            last_name=str(member.get("last_name") or "").strip(),
            first_name=str(member.get("first_name") or "").strip(),
            date_str=now_str,
            purchase_id=int(member["purchase_id"]),
        )
    except Exception:
        logger.exception("Attestation: sent date not recorded in SQLite")

    return AttestationSent(status="success", message=f"Attestation envoyée avec succès à {data.to_email}.",
                           email_sent_date=now_str, filename=filename_pdf)
