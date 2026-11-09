"""Attendance sheets: the groups offered by the export page and their headcounts, and the sheets themselves,
generated in memory. Knows nothing about HTTP: refusals are raised as domain.errors."""

from __future__ import annotations

import datetime
import io
import zipfile
from dataclasses import dataclass
from typing import List, Literal, Optional

from domain.constants import get_active_season, is_valid_season
from domain.errors import InvalidRequest
from domain.members.planning_groups import is_autonome_creneau
from domain.members.presence_rules import AutonomousCounts, count_autonomous, members_with_tarifs
from exports.presence_sheets import generate_presence_sheets
from infrastructure.sqlite.members import MemberRepository
from infrastructure.sqlite.planning import PlanningRepository

Variant = Literal["autonome", "cours"]


@dataclass(frozen=True)
class CourseGroup:
    name: str
    schedule: str  # its slots, "Lundi 18h-20h · Jeudi 18h-20h"
    tarifs: List[str]
    member_count: int


@dataclass(frozen=True)
class PresenceDownload:
    filename: str
    content: bytes
    is_zip: bool  # a ZIP of one workbook per course, else one Excel workbook


@dataclass(frozen=True)
class PresenceOverview:
    season: str
    autonomous_counts: AutonomousCounts
    autonomous_groups: List[str]
    courses: List[CourseGroup]


def presence_overview() -> PresenceOverview:
    """The groups of the active season: the autonomous ones with the headcount of their sheet, and each course."""
    season = get_active_season()
    creneaux = PlanningRepository.load_creneaux_groups()
    members = MemberRepository.load_direct_data(season)

    autonomous_creneaux = [c for c in creneaux if is_autonome_creneau(c)]
    autonomous_tarifs = {str(t).strip() for c in autonomous_creneaux for t in c.get("tarifs") or []}
    courses = [
        CourseGroup(
            name=str(c["groupe"]),
            schedule=" · ".join(f"{day} {hours}".strip() for day, hours in c["slots"] if day or hours),
            tarifs=[str(t) for t in c["tarifs"] or []],
            member_count=len(members_with_tarifs(members, c["tarifs"] or [])),
        )
        for c in creneaux if not is_autonome_creneau(c)
    ]
    return PresenceOverview(
        season=season,
        autonomous_counts=count_autonomous(members, autonomous_tarifs, datetime.date.today()),
        autonomous_groups=[str(c["groupe"]) for c in autonomous_creneaux],
        courses=courses,
    )


def _session_day(text: str) -> Optional[datetime.date]:
    """A dd/mm/yyyy date of the export request; None when empty."""
    if not text.strip():
        return None
    try:
        return datetime.datetime.strptime(text.strip(), "%d/%m/%Y").date()
    except ValueError as e:
        raise InvalidRequest("Date invalide (format attendu : JJ/MM/AAAA).") from e


def export_presence_sheets(variant: Variant, season: str, start_date: str, end_date: str, selected_groups: List[str],
                           show_health_col: bool, same_sheet: bool) -> PresenceDownload:
    """The attendance sheets asked for: one workbook, or a ZIP of one workbook per course.
    season: the active one when empty; dates (dd/mm/yyyy): the season's course dates when empty."""
    season = season or get_active_season()
    if not is_valid_season(season):
        raise InvalidRequest("Saison invalide (format attendu : AAAA-AAAA).")
    first_day, last_day = _session_day(start_date), _session_day(end_date)
    if first_day and last_day and first_day > last_day:
        raise InvalidRequest("La date de début doit précéder la date de fin.")

    autonomous = variant == "autonome"
    creneaux = [c for c in PlanningRepository.load_creneaux_groups() if is_autonome_creneau(c) == autonomous]
    if not autonomous and selected_groups:
        creneaux = [c for c in creneaux if c["groupe"] in selected_groups]
    if not creneaux:
        raise InvalidRequest("Aucun groupe sélectionné pour l'export.")

    files = generate_presence_sheets(
        [c["groupe"] for c in creneaux],
        MemberRepository.load_direct_data(season),
        PlanningRepository.load_planning_data(),
        variant=variant,
        first_day=first_day,
        last_day=last_day,
        group_tarifs={c["groupe"]: c["tarifs"] for c in creneaux},
        show_health_col=show_health_col,
        same_sheet=same_sheet,
    )
    if len(files) == 1:
        return PresenceDownload(files[0].filename, files[0].content, is_zip=False)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file in files:
            zip_file.writestr(file.filename, file.content)
    return PresenceDownload(f"Fiches_Presence_{variant.capitalize()}_{season}.zip", archive.getvalue(), is_zip=True)
