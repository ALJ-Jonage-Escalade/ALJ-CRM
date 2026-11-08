"""Competitions: list, create, partial update, delete, archive.

Controllers in src/api handle HTTP in and out only: business rules are in src/services,
whose errors become HTTP errors in api.responses.service_error_handler. Roles are checked
by the auth middleware (infrastructure.security.api_auth.required_role): reads are open to
readonly, writes need coach.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request
from fastapi.responses import Response

from api.responses import STORAGE_ERRORS, SUCCESS, document_responses, error_responses, json_with_etag
from api.competitions.schemas.competitions import CompetitionCreate, CompetitionFfmeLookup, CompetitionUpdate
from api.competitions.schemas.views import Competition, Done, PastArchived
from services.competitions.competitions import CompetitionService as Service
from services.documents import Doc

router = APIRouter(prefix="/api/competitions")

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_model=List[Competition], responses=error_responses(*STORAGE_ERRORS))
def list_competitions(request: Request) -> Response:
    return json_with_etag(request, Service.list_competitions())


@router.get("/lookup-ffme/{id_ffme}", response_model=CompetitionFfmeLookup, responses=error_responses(400, 404, 502))
def lookup_ffme_competition(id_ffme: str) -> Doc:
    return Service.lookup_ffme(id_ffme)


@router.post("", status_code=201, response_model=None, responses=document_responses(Competition, *STORAGE_ERRORS, status=201))
def create_competition(body: CompetitionCreate) -> Doc:
    return Service.create_competition(body.model_dump(exclude_none=True))


@router.patch("/{competition_id}", response_model=None, responses=document_responses(Competition, 404, *STORAGE_ERRORS))
def update_competition(competition_id: int, body: CompetitionUpdate) -> Doc:
    return Service.update_competition(competition_id, body.model_dump(exclude_unset=True))


@router.delete("/{competition_id}", response_model=Done, responses=error_responses(404, *STORAGE_ERRORS))
def delete_competition(competition_id: int) -> Doc:
    Service.delete_competition(competition_id)
    return SUCCESS


@router.post("/archive-past", response_model=PastArchived, responses=error_responses(*STORAGE_ERRORS))
def archive_past_competitions() -> Doc:
    return {**SUCCESS, "archived": Service.archive_past_competitions()}


@router.get("/{competition_id}/export-excel", response_class=Response,
            responses={200: {"content": {XLSX: {}}, "description": "Classeur Excel"}, **error_responses(404, *STORAGE_ERRORS)})
def export_competition_excel(competition_id: int) -> Response:
    content = Service.export_excel(competition_id)
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="competiteurs_{competition_id}.xlsx"'},
    )


@router.get("/{competition_id}/export-pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}, "text/html": {}}, "description": "Liste PDF (HTML sans WeasyPrint)"},
                       **error_responses(404, *STORAGE_ERRORS)})
def export_competition_pdf(competition_id: int) -> Response:
    content = Service.export_pdf(competition_id)
    # Without WeasyPrint the service answers the printable HTML page: named as such
    is_pdf = content.startswith(b"%PDF")
    media_type = "application/pdf" if is_pdf else "text/html; charset=utf-8"
    extension = "pdf" if is_pdf else "html"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="competiteurs_{competition_id}.{extension}"'},
    )
