"""HelloAsso membership campaign: a raw HelloAsso v5 item becomes a flat membership record.

Single reading of the membership form's items, shared by the membership dashboard and the members import
(plans/helloasso-membership-import.md). Pure: no HTTP, no database.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional

from domain.competitions.matching import parse_campaign_identifier
from domain.utils import is_helloasso_url, normalize_string

# Formats seen in the birth date field of the form (typed by families, or ISO from HelloAsso)
_BIRTH_DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y")


@dataclass(frozen=True)
class MembershipRecord:
    """One registration of the membership campaign (one person, one tariff)."""
    item_id: int
    order_ref: str
    order_date: str
    status: str
    tarif_name: str
    amount: float
    last_name: str
    first_name: str
    payer_last_name: str
    payer_first_name: str
    payer_email: str
    birth_date: str  # ISO date, "" when missing or unreadable
    birth_date_raw: str  # as typed on the form
    licence: str  # FFME licence, digits only
    options: Dict[str, float] = field(default_factory=dict)  # insurance option name -> amount in euros
    custom_fields: Dict[str, str] = field(default_factory=dict)


def _custom_value(custom_field: Mapping[str, Any]) -> str:  # Any: raw HelloAsso JSON
    """The answer of a custom field: HelloAsso puts it in `answer` or in `value`."""
    value = custom_field.get("answer")
    if value is None or not str(value).strip():
        value = custom_field.get("value")
    return str(value or "").strip()


def parse_birth_date(raw: str) -> str:
    """ISO date of a birth date typed on the form, "" when it cannot be read."""
    text = str(raw or "").strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    for date_format in _BIRTH_DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return ""


def _field_by_words(custom_fields: Mapping[str, str], *words: str) -> str:
    """Value of the first custom field whose (normalised) name contains every word."""
    for name, value in custom_fields.items():
        normalized = normalize_string(name)
        if all(word in normalized for word in words):
            return value
    return ""


def map_membership_item(item: Mapping[str, Any]) -> MembershipRecord:  # Any: raw HelloAsso JSON
    order = item.get("order") or {}
    user = item.get("user") or {}
    payer = item.get("payer") or {}
    custom_fields = {str(f.get("name") or ""): _custom_value(f) for f in item.get("customFields") or []}
    birth_date_raw = _field_by_words(custom_fields, "naissance")
    return MembershipRecord(
        item_id=int(item.get("id") or 0),
        order_ref=str(order.get("id") or "").strip(),
        order_date=str(order.get("date") or "").strip(),
        status=str(item.get("state") or "").strip(),
        tarif_name=str(item.get("name") or "").strip(),
        amount=(item.get("amount") or 0) / 100,
        last_name=str(user.get("lastName") or "").strip(),
        first_name=str(user.get("firstName") or "").strip(),
        payer_last_name=str(payer.get("lastName") or "").strip(),
        payer_first_name=str(payer.get("firstName") or "").strip(),
        payer_email=str(payer.get("email") or "").strip(),
        birth_date=parse_birth_date(birth_date_raw),
        birth_date_raw=birth_date_raw,
        licence=re.sub(r"\D", "", _field_by_words(custom_fields, "licence")),
        options={str(o.get("name") or "").strip(): (o.get("amount") or 0) / 100 for o in item.get("options") or []},
        custom_fields=custom_fields,
    )


# Item types of a membership form that are registrations (the others: donations, extra products…)
REGISTRATION_TYPES = ("Registration", "Membership")


def map_membership_items(items: Iterable[Mapping[str, Any]]) -> list[MembershipRecord]:  # Any: raw HelloAsso JSON
    """The registrations of a membership form's items, mapped."""
    return [map_membership_item(item) for item in items if item.get("type") in REGISTRATION_TYPES]



# ---------------------------------------------------------------------------
# Campaign (app setting HELLOASSO_MEMBERSHIP_CAMPAIGN) and season guard
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MembershipCampaign:
    form_type: str  # HelloAsso form type ("Membership" for the club's membership form)
    slug: str


def default_membership_campaign(season: str) -> str:
    """Slug the club gives its membership form each season, used when nothing is configured."""
    return f"adhesion-escalade-{season}-amicale-laique-escalade-2"


def parse_membership_campaign(reference: str) -> MembershipCampaign:
    """The form of a campaign reference: a HelloAsso URL, "FormType:slug" or a bare slug (a membership form).
    Raises ValueError when the reference cannot be read."""
    raw = str(reference or "").strip()
    if not is_helloasso_url(raw) and ":" not in raw:
        raw = f"Membership:{raw}" if raw else raw
    identifier = parse_campaign_identifier(raw)
    return MembershipCampaign(form_type=identifier["form_type"], slug=identifier["slug"])


def season_guard(slug: str, season: str) -> Optional[str]:
    """Why the campaign cannot feed this season (its slug does not name both years of the season), None when it can."""
    years = season.split("-")
    if all(year in slug for year in years):
        return None
    return f"La campagne « {slug} » ne correspond pas à la saison active {season} : import bloqué."
