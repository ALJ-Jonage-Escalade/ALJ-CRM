"""Bodies of the member and season routes called by the Vue app (API contract, see api/communications/schemas.py)."""

from __future__ import annotations

import re
from typing import Annotated, List, Literal, Optional, Union

from pydantic import AfterValidator, BaseModel, Field, WithJsonSchema, field_validator

from api.request_body import RequestBody
from domain.members.countries import country_names, nationality_names
from domain.members.ffme_category import Category
from domain.members.sex import Sex


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


class MemberKey(BaseModel):
    """The club key a member holds, since when."""
    id: int
    code: str
    given_on: str


class EmergencyContact(RequestBody):
    """Someone to call for a member. Blank rows are dropped when saved: a row holds a name, a phone or both."""
    name: str = ""
    phone: str = ""


def _one_of(choices: List[str], field_label: str) -> AfterValidator:
    def check(value: str) -> str:
        if value and value not in choices:
            raise ValueError(f"{field_label} inconnu(e) : {value}")
        return value
    return AfterValidator(check)


# The choices of the member form (domain/members/countries.py), "" to clear; an enum in the API contract
CountryName = Annotated[str, _one_of(country_names(), "pays"),
                        WithJsonSchema({"type": "string", "enum": ["", *country_names()]})]
NationalityName = Annotated[str, _one_of(nationality_names(), "nationalité"),
                            WithJsonSchema({"type": "string", "enum": ["", *nationality_names()]})]


class Member(BaseModel):
    """One member of a season (one purchase), as domain/members/view.py member_row() builds it.
    Names, city and phones are already formatted; status_norm is the French status label."""
    user_id: int
    purchase_id: int
    helloasso_item_id: Optional[int] = Field(description="The HelloAsso registration the membership comes from, None when entered by hand")
    season_name: str
    last_name: str
    first_name: str
    birth_date: str
    age: Optional[int]
    sex: Optional[Sex] = Field(description="FFME sex, None when not given")
    address: str
    zip_code: str
    city: str
    country: str = Field(description="As stored (HelloAsso free text or a choice of the form)")
    nationality: str = Field(description="As stored (HelloAsso free text or a choice of the form)")
    phone: str
    email_primary: str
    email_secondary: str
    licence_ffme: str
    ffme_category: Union[Category, Literal[""]] = Field(description="FFME competition category, \"\" when none")
    emergency_contacts: List[EmergencyContact] = Field(description="In order, the first one is the main one")
    emergency1_name: str = Field(description="Deprecated: first contact, for tabs of the previous build until release B")
    emergency1_phone: str = Field(description="Deprecated: first contact, for tabs of the previous build until release B")
    emergency2_name: str = Field(description="Deprecated: second contact, for tabs of the previous build until release B")
    emergency2_phone: str = Field(description="Deprecated: second contact, for tabs of the previous build until release B")
    health_commitment: str
    document_sante: str
    photo_auth: str
    badge_rouge: str
    autonomie_bloc: str
    key: Optional[MemberKey] = None  # the club key they hold (Outils › Clés)
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
    creneau_details: str


class CompetitorContact(BaseModel):
    """Contacts of a participant of an open competition (domain/members/view.py competitor_contacts): the only
    member data kept offline on a coach's phone."""
    adherent_id: int
    last_name: str
    first_name: str
    phone: str
    creneau_groupe: str
    emergency_contacts: List[EmergencyContact] = Field(description="In order, the first one is the main one")
    emergency1_name: str = Field(description="Deprecated: first contact, for tabs of the previous build until release B")
    emergency1_phone: str = Field(description="Deprecated: first contact, for tabs of the previous build until release B")
    emergency2_name: str = Field(description="Deprecated: second contact, for tabs of the previous build until release B")
    emergency2_phone: str = Field(description="Deprecated: second contact, for tabs of the previous build until release B")


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
    last_name: Optional[str] = Field(default=None, min_length=1)
    first_name: Optional[str] = Field(default=None, min_length=1)
    birth_date: Optional[str] = Field(default=None, pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    status: Optional[MemberStatus] = None
    amount: Optional[float] = Field(default=None, ge=0)
    licence_ffme: Optional[str] = None
    sex: Optional[Sex] = Field(default=None, description="Sent as null to clear it")
    ffme_category: Optional[Union[Category, Literal[""]]] = Field(
        default=None, description="\"\" clears it; left out with a new birth_date: recomputed for the member's latest season")
    badge_rouge: Optional[YesNo] = None
    autonomie_bloc: Optional[YesNo] = None
    photo_auth: Optional[YesNo] = None
    email_primary: Optional[str] = None
    email_secondary: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    zip_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[CountryName] = None
    nationality: Optional[NationalityName] = None
    emergency_contacts: Optional[List[EmergencyContact]] = Field(default=None, description="Replaces the whole list, in this order; [] removes every contact")
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
    sex: Optional[Sex] = None
    tarif_name: str = ""
    status: MemberStatus = "Validé"
    amount: float = Field(default=0.0, ge=0)
    licence_ffme: str = ""
    badge_rouge: YesNo = "Non"
    autonomie_bloc: YesNo = "Non"
    photo_auth: YesNo = "Oui"
    email_primary: str = ""
    email_secondary: str = ""
    phone: str = ""
    address: str = ""
    zip_code: str = ""
    city: str = ""
    country: CountryName = "France"
    nationality: NationalityName = ""
    emergency_contacts: List[EmergencyContact] = Field(default_factory=list, description="In order, the first one is the main one")
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


class HelloAssoDetach(BaseModel):
    """Why the admin detaches a membership from its HelloAsso registration (required, kept in the import history)."""
    reason: str


class HelloAssoDetached(BaseModel):
    """The membership deleted: its HelloAsso registration is to be attached again from the import."""
    status: str
    message: str
    order_ref: str
    season: str
