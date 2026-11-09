"""FFME federal CSV export (strict format, see tests/exports/test_ffme_golden_master.py) and
Excel import of the FFME license list, matched against the members (admin for writes)."""

from __future__ import annotations

import base64
import binascii
import datetime
from typing import List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import Response

from api.ffme.schemas import FfmeFile, FfmeImportRequest, FfmeImportResult, FfmeLicensee, FfmeMatchStats, FfmeMember, FfmePreview, FfmeStats
from api.responses import error_responses, file_download
from domain.constants import resolve_season
from domain.errors import InvalidRequest
from infrastructure.sqlite.ffme_import import FfmeMatch
from services.members import ffme

router = APIRouter()

UNREADABLE_FILE = "Fichier illisible : il doit s'agir d'un fichier Excel encodé en base64."


def _decoded(content_base64: str) -> bytes:
    try:
        return base64.b64decode(content_base64, validate=True)
    except binascii.Error as e:
        raise InvalidRequest(UNREADABLE_FILE) from e


def _match_stats(stats: ffme.MatchStats, matched_manually: int = 0) -> FfmeMatchStats:
    return FfmeMatchStats(**stats, matched_manually=matched_manually)


@router.get("/api/ffme/stats", response_model=FfmeStats, responses=error_responses(400))
def get_ffme_stats_api(season: Optional[str] = None) -> FfmeStats:
    """Members of the season that the federal CSV export would declare, and those it leaves out."""
    target_season = resolve_season(season)
    return FfmeStats(status="success", season=target_season, **ffme.export_stats(target_season))


@router.get("/api/ffme/export", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "Fichier CSV FFME"}, **error_responses(400)})
def export_ffme_api(season: Optional[str] = None, include_termine: bool = Query(True)) -> Response:
    """Génère le fichier CSV d'import FFME et le renvoie directement en téléchargement."""
    content = ffme.export_csv(resolve_season(season), include_termine)
    filename = f"import_ffme_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return file_download(content, filename, "text/csv; charset=utf-8")


@router.post("/api/ffme/preview", response_model=FfmePreview, responses=error_responses(400))
def preview_ffme_import_api(data: FfmeFile) -> FfmePreview:
    """Analyse un fichier Excel FFME et prépare le rapprochement sans modifier la base."""
    if not data.content_base64:
        raise InvalidRequest("Fichier Excel manquant (content_base64 obligatoire).")
    preparation = ffme.prepare_licensees(_decoded(data.content_base64))
    stats = preparation["stats"]
    if stats["errors"] and not preparation["updates"]:
        raise InvalidRequest(stats["errors"][0])
    unmatched = [FfmeLicensee(**{k: str(row.get(k) or "") for k in FfmeLicensee.model_fields}) for row in preparation["unmatched"]]
    users = [FfmeMember(id=int(u["id"]), last_name=str(u["last_name"] or ""), first_name=str(u["first_name"] or ""),
                        birth_date=str(u["birth_date"] or "")) for u in preparation["users"]]
    return FfmePreview(
        status="success",
        filename=data.filename,
        stats=_match_stats(stats),
        matched_count=len(preparation["updates"]),
        unmatched_count=len(unmatched),
        unmatched=unmatched,
        users=users,
    )


@router.post("/api/ffme/import", response_model=FfmeImportResult, responses=error_responses(400))
def apply_ffme_import_api(data: FfmeImportRequest) -> FfmeImportResult:
    """Applique l'importation FFME en BDD : rapprochements automatiques du fichier (recalculés ici, comme
    dans l'aperçu) et associations manuelles choisies par le bureau."""
    season = resolve_season(data.season)
    excel_content = _decoded(data.content_base64) if data.content_base64 else None
    manual_matches: List[FfmeMatch] = [
        (ffme.STATUS_DONE, m.licence, m.passeports, m.diplomes, m.document_sante, m.user_id) for m in data.manual_matches]
    updated_count, stats = ffme.apply_import(season, excel_content, manual_matches)
    return FfmeImportResult(
        status="success",
        message=f"Importation FFME validée : {updated_count} adhérents mis à jour.",
        updated_count=updated_count,
        matched_manually=len(manual_matches),
        season=season,
        stats=_match_stats(stats, len(manual_matches)),
    )
