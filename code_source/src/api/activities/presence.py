"""Attendance sheets (Excel), generated in memory and downloaded straight into the browser."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from api.activities.schemas import PresenceAutonomous, PresenceConfig, PresenceCourse, PresenceDates, PresenceExportRequest
from api.responses import XLSX, error_responses, file_download
from exports.presence_sheets import SEASON_COURSE_END, SEASON_COURSE_START
from services.activities import presence

router = APIRouter()


@router.get("/api/presence/config", response_model=PresenceConfig)
def get_presence_config() -> PresenceConfig:
    """Renvoie les groupes disponibles (autonomes et cours) et leurs statistiques pour l'IHM."""
    overview = presence.presence_overview()
    counts = overview.autonomous_counts
    return PresenceConfig(
        status="success",
        season=overview.season,
        default_dates=PresenceDates(start=SEASON_COURSE_START.strftime("%d/%m/%Y"), end=SEASON_COURSE_END.strftime("%d/%m/%Y")),
        autonome=PresenceAutonomous(
            adultes=counts.adults,
            mineurs=counts.minors,
            mineurs_autorises=counts.authorized_minors,
            total=counts.total,
            groups=overview.autonomous_groups,
        ),
        cours=[PresenceCourse(groupe=c.name, slots=c.schedule, tarifs=c.tarifs, count=c.member_count) for c in overview.courses],
    )


@router.post("/api/presence/export", response_class=Response,
             responses={200: {"content": {XLSX: {}, "application/zip": {}}, "description": "Classeur Excel, ou archive ZIP d'un classeur par cours"},
                        **error_responses(400)})
def export_presence_api(data: PresenceExportRequest) -> Response:
    """Génère les fiches de présence au format Excel et les renvoie directement en téléchargement."""
    sheets = presence.export_presence_sheets(data.variant, data.season, data.start_date, data.end_date, data.selected_groups,
                                             data.show_health_col, data.same_sheet)
    return file_download(sheets.content, sheets.filename, "application/zip" if sheets.is_zip else XLSX)
