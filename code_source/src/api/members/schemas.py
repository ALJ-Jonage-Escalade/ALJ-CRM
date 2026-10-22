"""Bodies of the membership season routes called by the Vue app (API contract, see api/communications/schemas.py)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class SeasonTarifs(BaseModel):
    """The season's HelloAsso tariffs, to link them to a planning slot."""
    status: Literal["success"]
    season: str
    tarifs: List[str]


class Seasons(BaseModel):
    """Season names, most recent first, and the active season."""
    seasons: List[str]
    active: str


class Creneau(BaseModel):
    """A slot group of the planning and the HelloAsso tariffs it covers."""
    groupe: str
    tarifs: List[str]
    categorie_age: str
    type: str


class Member(BaseModel):
    """One member of a season (one purchase), as domain/members/view.py member_row() builds it.
    Names, city and phones are already formatted; status_norm is the French status label."""
    user_id: int
    purchase_id: int
    season_name: str
    last_name: str
    first_name: str
    birth_date: str
    age: Optional[int]
    gender: str
    address: str
    zip_code: str
    city: str
    phone: str
    email_primary: str
    email_secondary: str
    licence_ffme: str
    emergency1_name: str
    emergency1_phone: str
    emergency2_name: str
    emergency2_phone: str
    health_commitment: str
    document_sante: str
    photo_auth: str
    badge_rouge: str
    autonomie_bloc: str
    passeport_orange: str
    raw_passports: str
    raw_diplomas: str
    payer: str
    payer_email: str
    order_ref: str
    order_date: str
    tarif_name: str
    amount: Optional[float]
    status: str
    status_norm: str
    email_sent_date: str
    commentaires_correctif: str
    creneau_groupe: str
    categorie: str
    creneau_details: str


class MemberList(BaseModel):
    """The members of one season, sorted by name, with the planning's slot groups (filters of the list)."""
    season: str
    members: List[Member]
    creneaux: List[Creneau]
