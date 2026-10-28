"""Bodies of the report routes (members map and pivot table of the Outils page in the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from domain.members.sex import Sex


class MapMember(BaseModel):
    """A member living at a map point. name: "First LAST"; group: the HelloAsso tariff ("Aucun" without one)."""
    name: str
    group: str


class MapPoint(BaseModel):
    """Geocoded address shared by one or more members. address: as shown in the popup."""
    address: str
    lat: float
    lon: float
    members: List[MapMember]


class MapPoints(BaseModel):
    """Members of a season placed on the map. season: the season actually read (the active one for "active").
    Addresses not geocoded yet are left out (geocoded in the background, on the map at the next load)."""
    season: str
    points: List[MapPoint]


class PivotRecord(BaseModel):
    """A member (one purchase) as a row of the pivot table. The JSON keys are the French field names shown by the
    table (aliases); age: at the start of the row's season, None when the birth date is unknown."""

    last_name: str = Field(serialization_alias="Nom")
    first_name: str = Field(serialization_alias="Prénom")
    sex: Optional[Sex] = Field(serialization_alias="Sexe", description="None when not given (the page labels it)")
    age: Optional[int] = Field(serialization_alias="Âge")
    age_band: str = Field(serialization_alias="Tranche d'Âge")
    city: str = Field(serialization_alias="Ville")
    group: str = Field(serialization_alias="Groupe / Tarif")
    status: str = Field(serialization_alias="Statut")
    season: str = Field(serialization_alias="Saison")
    membership_type: str = Field(serialization_alias="Type d'Adhésion")
    order_date: str = Field(serialization_alias="Date d'Inscription")
    order_month: str = Field(serialization_alias="Mois d'Inscription")


class PivotRecords(BaseModel):
    """Members of a season for the pivot table. season: the season actually read (the active one for "active")."""
    season: str
    records: List[PivotRecord]
