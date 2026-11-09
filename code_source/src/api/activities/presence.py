"""Attendance sheets (Excel), generated in memory and downloaded straight into the browser."""

from __future__ import annotations

import datetime
import io
import zipfile
from typing import Optional, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from api.activities.schemas import PresenceAutonomous, PresenceConfig, PresenceCourse, PresenceDates, PresenceExportRequest
from api.responses import XLSX, error, error_responses, file_download
from domain.constants import get_active_season, is_valid_season
from domain.members.planning_groups import is_autonome_creneau
from domain.members.presence_rules import count_autonomous, members_with_tarifs
from exports.presence_sheets import SEASON_COURSE_END, SEASON_COURSE_START, generate_presence_sheets
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.planning import PlanningRepository

router = APIRouter()


@router.get("/api/presence/config", response_model=PresenceConfig, responses=error_responses(500))
def get_presence_config() -> Union[PresenceConfig, JSONResponse]:
    """Renvoie les groupes disponibles (autonomes et cours) et leurs statistiques pour l'IHM."""
    season = get_active_season()
    creneaux = PlanningRepository.load_creneaux_groups()
    members = MemberRepository.load_direct_data(season_filter=season)

    autonomous_creneaux = [c for c in creneaux if is_autonome_creneau(c)]
    autonomous_tarifs = {str(t).strip() for c in autonomous_creneaux for t in c.get("tarifs") or []}
    counts = count_autonomous(members, autonomous_tarifs, datetime.date.today())

    courses = [
        PresenceCourse(
            groupe=str(c["groupe"]),
            slots=" · ".join(f"{day} {hours}".strip() for day, hours in c["slots"] if day or hours),
            tarifs=[str(t) for t in c["tarifs"] or []],
            count=len(members_with_tarifs(members, c["tarifs"] or [])),
        )
        for c in creneaux if not is_autonome_creneau(c)
    ]
    return PresenceConfig(
        status="success",
        season=season,
        default_dates=PresenceDates(start=SEASON_COURSE_START.strftime("%d/%m/%Y"), end=SEASON_COURSE_END.strftime("%d/%m/%Y")),
        autonome=PresenceAutonomous(
            adultes=counts.adults,
            mineurs=counts.minors,
            mineurs_autorises=counts.authorized_minors,
            total=counts.total,
            groups=[str(c["groupe"]) for c in autonomous_creneaux],
        ),
        cours=courses,
    )


def _session_day(text: str) -> Optional[datetime.date]:
    """A dd/mm/yyyy date of the export request; None when empty, ValueError when malformed."""
    return datetime.datetime.strptime(text.strip(), "%d/%m/%Y").date() if text.strip() else None


@router.post("/api/presence/export", response_class=Response,
             responses={200: {"content": {XLSX: {}, "application/zip": {}}, "description": "Classeur Excel, ou archive ZIP d'un classeur par cours"},
                        **error_responses(400, 500)})
def export_presence_api(data: PresenceExportRequest) -> Response:
    """Génère les fiches de présence au format Excel et les renvoie directement en téléchargement."""
    season = data.season or get_active_season()
    if not is_valid_season(season):
        return error(400, "Saison invalide (format attendu : AAAA-AAAA).")
    try:
        first_day, last_day = _session_day(data.start_date), _session_day(data.end_date)
    except ValueError:
        return error(400, "Date invalide (format attendu : JJ/MM/AAAA).")
    if first_day and last_day and first_day > last_day:
        return error(400, "La date de début doit précéder la date de fin.")
    members = MemberRepository.load_direct_data(season_filter=season)
    planning = PlanningRepository.load_planning_data()

    autonomous = data.variant == "autonome"
    creneaux = [c for c in PlanningRepository.load_creneaux_groups() if is_autonome_creneau(c) == autonomous]
    if not autonomous and data.selected_groups:
        creneaux = [c for c in creneaux if c["groupe"] in data.selected_groups]
    if not creneaux:
        return error(400, "Aucun groupe sélectionné pour l'export.")

    files = generate_presence_sheets(
        [c["groupe"] for c in creneaux],
        members,
        planning,
        variant=data.variant,
        first_day=first_day,
        last_day=last_day,
        group_tarifs={c["groupe"]: c["tarifs"] for c in creneaux},
        show_health_col=data.show_health_col,
        same_sheet=data.same_sheet,
    )
    if len(files) == 1:
        return file_download(files[0].content, files[0].filename, XLSX)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in files:
            zip_file.writestr(file.filename, file.content)
    return file_download(archive.getvalue(), f"Fiches_Presence_{data.variant.capitalize()}_{season}.zip", "application/zip")
