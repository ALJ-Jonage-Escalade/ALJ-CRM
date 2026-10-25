"""Bodies of the report routes (members map of the Outils page in the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel


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
