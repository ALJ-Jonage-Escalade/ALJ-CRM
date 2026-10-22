"""Bodies of the planning routes (Planning page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel

from api.request_body import RequestBody


class PlanningSlot(BaseModel):
    """A weekly slot. jour: a day ("Lundi"…), or several ("Lundi / Jeudi"); horaires: "18:00 - 20:00".
    helloasso_tarifs: the HelloAsso tariffs of its members; naissance_min/max: birth year or date bounds."""
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


class PlanningSlotSaved(BaseModel):
    status: Literal["success"]
    message: str
    item: PlanningSlot


class PlanningSlotDeleted(BaseModel):
    status: Literal["success"]
    message: str
