"""Payment certificates as PDF, one member at a time (admin): generated in memory, never stored.
The rules and the sending are in services/communications/attestations.py."""

from __future__ import annotations

import unicodedata
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.auth.me import author_of
from api.communications.schemas import AttestationRequest, AttestationSend, AttestationSent
from api.responses import error_responses
from services.communications import attestations

router = APIRouter()

_PDF: dict[int | str, dict[str, Any]] = {  # Any: FastAPI's `responses` format
    200: {"content": {"application/pdf": {}}, "description": "The certificate (PDF)"}}


def _content_disposition(filename: str) -> str:
    """Header of the PDF: HTTP headers are Latin-1, so an ASCII name plus the UTF-8 one (RFC 6266) for accented names."""
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


@router.post("/api/attestations/preview", response_class=Response, responses={**_PDF, **error_responses(400, 404, 500)})
def preview_attestation_api(data: AttestationRequest) -> Response:
    """Génère l'aperçu PDF d'une attestation de paiement (retourne application/pdf)."""
    member = attestations.attestation_member(data.season, data.purchase_id)  # 400, 404: service error handler
    return Response(content=attestations.attestation_pdf(member), media_type="application/pdf",
                    headers={"Content-Disposition": _content_disposition(attestations.attestation_filename(member))})


@router.post("/api/attestations/send", response_model=AttestationSent, responses=error_responses(400, 403, 404, 500, 502))
def send_attestation_api(request: Request, data: AttestationSend) -> AttestationSent:
    """Génère une attestation PDF en mémoire, l'envoie par e-mail et met à jour la date d'envoi."""
    sent = attestations.send_attestation(data.season, data.purchase_id, data.to_email, author_of(request),
                                         template_name=data.template_name, subject=data.subject, body=data.body,
                                         add_signature=data.add_signature)
    return AttestationSent(status="success", **sent)
