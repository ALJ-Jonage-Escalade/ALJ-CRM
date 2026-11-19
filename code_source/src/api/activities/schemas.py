"""Bodies of the planning routes (Planning page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

from api.request_body import RequestBody


class PlanningSlot(BaseModel):
    """A weekly slot. jour: a day ("Lundi"…), or several ("Lundi / Jeudi"); horaires: "18:00 - 20:00".
    helloasso_tarifs: the HelloAsso tariffs of its members; naissance_min/max: birth year or date bounds;
    seance_autonome: its members are listed on the autonomous attendance sheet."""
    id: int
    groupe: str
    type: str
    categorie_age: str
    jour: str
    horaires: str
    encadrants: List[str]
    helloasso_tarifs: List[str]
    whatsapp_link: str
    naissance_min: str
    naissance_max: str
    seance_autonome: bool


class PlanningSlotUpdate(RequestBody):
    """id: 0 for a new slot."""
    id: int = 0
    groupe: str = ""
    type: str = ""
    categorie_age: str = ""
    jour: str = ""
    horaires: str = ""
    encadrants: List[str] = []
    helloasso_tarifs: List[str] = []
    whatsapp_link: str = ""
    naissance_min: str = ""
    naissance_max: str = ""
    seance_autonome: bool = False


class PlanningSlotSaved(BaseModel):
    status: Literal["success"]
    message: str
    item: PlanningSlot


class PlanningSlotDeleted(BaseModel):
    status: Literal["success"]
    message: str


class PresenceDates(BaseModel):
    """Default period of the sheets (dd/mm/yyyy)."""
    start: str
    end: str


class PresenceAutonomous(BaseModel):
    """Members of the autonomous slots, plus the minors of other groups allowed to climb on their own.
    groups: the autonomous groups; extra_groups: the course groups ticked « Séance autonome », added to the sheet."""
    adultes: int
    mineurs: int
    mineurs_autorises: int
    total: int
    groups: List[str]
    extra_groups: List[str]


class PresenceCourse(BaseModel):
    """A supervised course. slots: "Lundi 18:00 - 20:00 · Jeudi …"; count: its members."""
    groupe: str
    slots: str
    tarifs: List[str]
    count: int


class PresenceConfig(BaseModel):
    status: Literal["success"]
    season: str
    default_dates: PresenceDates
    autonome: PresenceAutonomous
    cours: List[PresenceCourse]


class PresenceExportRequest(RequestBody):
    """Attendance sheets to generate. season: the active one when empty; dates: dd/mm/yyyy, the season's when empty.
    cours only: selected_groups (all the courses when empty) and same_sheet (one workbook, else a ZIP of one file per course)."""
    variant: Literal["autonome", "cours"] = "cours"
    season: str = ""
    start_date: str = ""
    end_date: str = ""
    show_health_col: bool = False
    selected_groups: List[str] = []
    same_sheet: bool = True
