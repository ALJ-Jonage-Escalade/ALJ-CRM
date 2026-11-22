"""Bodies of the report routes (members map and member statistics of the Outils page in the Vue app).

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


class MemberStatsRecord(BaseModel):
    """A purchase as a row of the member statistics, without names. age: at the start of the row's season, None
    without a birth date; status: Validé, Annulé, Refusé or the status as written; returning: already a member;
    order_month: YYYY-MM or « Inconnue »."""
    user_id: int
    sex: Optional[Sex] = Field(description="None when not given (the page labels it)")
    age: Optional[int]
    age_band: str
    city: str
    group: str
    status: str
    season: str
    returning: bool
    order_month: str


class MemberStatsRecords(BaseModel):
    """Every purchase of every season (cancelled and refused ones included)."""
    records: List[MemberStatsRecord]
