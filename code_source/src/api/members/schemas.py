"""Bodies of the member and season routes called by the Vue app (API contract, see api/communications/schemas.py)."""

from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from api.request_body import RequestBody


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


# ---------------------------------------------------------------- Member record (admin): edit and add

YesNo = Literal["Oui", "Non"]
# Statuses an admin may set (the list's status_norm labels)
MemberStatus = Literal["Validé", "Traité", "En cours", "Terminé", "Annulé"]
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _email_or_empty(value: Optional[str]) -> Optional[str]:
    if value and not _EMAIL.match(value):
        raise ValueError("adresse e-mail invalide")
    return value


class MemberChanges(RequestBody):
    """Fields of a member record to change; a field left out is kept (only the given ones are written)."""
    status: Optional[MemberStatus] = None
    licence_ffme: Optional[str] = None
    badge_rouge: Optional[YesNo] = None
    autonomie_bloc: Optional[YesNo] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    tarif_name: Optional[str] = Field(default=None, min_length=1)
    commentaires_correctif: Optional[str] = None

    check_emails = field_validator("email_primary", "email_secondary")(_email_or_empty)


class MemberUpdate(RequestBody):
    """The purchase (one membership of a season) and its member; purchase_id is enough, the others are fallbacks."""
    user_id: Optional[int] = None
    purchase_id: Optional[int] = None
    order_ref: Optional[str] = None
    fields: MemberChanges


class MemberUpdated(BaseModel):
    status: Literal["success"]
    message: str


class NewMember(RequestBody):
    """A member added by hand. Name, birth date and tariff are required (checked by the route, with its messages)."""
    last_name: str = ""
    first_name: str = ""
    birth_date: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    gender: Literal["Homme", "Femme", ""] = ""
    tarif_name: str = ""
    status: MemberStatus = "Validé"
    amount: float = Field(default=0.0, ge=0)
    licence_ffme: str = ""
    badge_rouge: YesNo = "Non"
    autonomie_bloc: YesNo = "Non"
    email_primary: str = ""
    email_secondary: str = ""
    phone: str = ""
    address: str = ""
    zip_code: str = ""
    city: str = ""
    emergency1_name: str = ""
    emergency1_phone: str = ""
    commentaires_correctif: str = ""

    check_emails = field_validator("email_primary", "email_secondary")(_email_or_empty)


class MemberCreate(RequestBody):
    """season: the active season when empty."""
    season: str = ""
    fields: NewMember


class MemberCreated(BaseModel):
    status: Literal["success"]
    message: str
    order_ref: str
    season: str
