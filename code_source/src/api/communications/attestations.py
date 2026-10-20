"""Payment certificates as PDF, one member at a time (admin): generated in memory, never stored."""

from __future__ import annotations

import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse, Response

from api.responses import error, internal_error

router = APIRouter()


@router.post("/api/attestations/preview")
def preview_attestation_api(data: Dict[str, Any] = Body(...)):
    """Génère l'aperçu PDF d'une attestation de paiement (retourne application/pdf)."""
    try:
        from domain.attestation.document import attestation_error, build_attestation, render_attestation_pdf, get_safe_pdf_filename
        member = data.get("member") or {}
        season = data.get("season")
        date_jour = data.get("date_jour")
        problem = attestation_error(member)
        if problem:
            return error(400, problem)

        html = build_attestation(member, season=season, date_jour=date_jour)
        pdf_bytes = render_attestation_pdf(html)

        last_name = member.get("last_name") or member.get("user_last_name") or "ADHERENT"
        first_name = member.get("first_name") or member.get("user_first_name") or ""
        order_ref = member.get("order_ref")
        filename = get_safe_pdf_filename(last_name, first_name, order_ref)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "preview_attestation_api")})


@router.post("/api/attestations/send")
def send_attestation_api(data: Dict[str, Any] = Body(...)):
    """Génère une attestation PDF en mémoire, l'envoie par e-mail et met à jour la date d'envoi."""
    try:
        from domain.attestation.document import attestation_error, build_attestation, render_attestation_pdf, get_safe_pdf_filename
        from domain.utils import apply_template_variables
        from infrastructure.mail.repository import EmailRepository

        member = data.get("member") or {}
        season = data.get("season")
        to_email = (data.get("to_email") or member.get("email_primary") or "").strip()
        if not to_email or "@" not in to_email:
            return JSONResponse(status_code=400, content={"status": "error", "message": "Adresse e-mail du destinataire invalide ou manquante."})
        problem = attestation_error(member)
        if problem:
            return error(400, problem)

        html = build_attestation(member, season=season)
        pdf_bytes = render_attestation_pdf(html)

        last_name = member.get("last_name") or member.get("user_last_name") or "ADHERENT"
        first_name = member.get("first_name") or member.get("user_first_name") or ""
        order_ref = member.get("order_ref")
        filename_pdf = get_safe_pdf_filename(last_name, first_name, order_ref)

        template_name = (data.get("template_name") or "Attestation échéance").strip()
        from infrastructure.mail.dispatch import EmailDispatchService
        tmpl = EmailDispatchService.get_template_by_name(template_name)

        raw_subject = data.get("subject") or (tmpl.get("subject") if tmpl else None) or "Attestation de paiement et d'échéance - Amicale Laïque de Jonage"
        raw_body = data.get("body") or (tmpl.get("body") if tmpl else None) or (
            "Bonjour {first_name},\n\n"
            "Nous avons le plaisir de vous transmettre en pièce jointe l'attestation de paiement pour votre adhésion ou celle de votre enfant à la section escalade de l'Amicale Laïque de Jonage.\n\n"
            "Sportivement,\n"
            "L'équipe ALJ Escalade"
        )
        subject = apply_template_variables(raw_subject, member)
        body = apply_template_variables(raw_body, member)

        sender_email = data.get("sender_email") or (tmpl.get("sender_email") if tmpl else None) or "inscription@alj-escalade.fr"
        if not EmailDispatchService.is_allowed_sender(sender_email):
            return JSONResponse(status_code=403, content={
                "status": "error", "message": f"Adresse d'expédition non autorisée : {sender_email}"})
        sender_name = data.get("sender_name") or (tmpl.get("sender_name") if tmpl else None) or "Amicale Laïque Jonage - Inscriptions"

        add_signature = data.get("add_signature", True)
        from infrastructure.mail.html_body import build_email_html, build_signature_plain, get_inline_images
        # HTML built from the template, then personalised with escaped values
        html_body = apply_template_variables(
            build_email_html(raw_body, add_signature=True, image_src_mode="cid"), member, escape_html=True
        ) if add_signature else None
        plain_body = body + ("\n\n" + build_signature_plain() if add_signature else "")
        inline_images = get_inline_images() if add_signature else []

        ok = EmailRepository.send_email(
            to_email=to_email,
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
            return JSONResponse(status_code=500, content={"status": "error", "message": "Échec d'envoi de l'e-mail."})

        # Enregistrement de la date d'envoi de l'attestation dans SQLite
        # (CloudDatabase.after_write synchronisera automatiquement la modification vers Firestore)
        now_str = datetime.datetime.now().strftime("%d/%m/%Y")
        try:
            from infrastructure.sqlite.repository import SqliteRepository
            pid = member.get("purchase_id")
            SqliteRepository.update_email_sent_date(
                order_ref=str(order_ref or "").strip(),
                last_name=str(last_name or "").strip(),
                first_name=str(first_name or "").strip(),
                date_str=now_str,
                purchase_id=int(pid) if pid is not None else None
            )
        except Exception as db_err:
            print(f"⚠️ [ATTESTATION] Erreur enregistrement date d'envoi dans SQLite : {db_err}")

        return {
            "status": "success",
            "message": f"Attestation envoyée avec succès à {to_email}.",
            "email_sent_date": now_str,
            "filename": filename_pdf
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": internal_error(e, "send_attestation_api")})
