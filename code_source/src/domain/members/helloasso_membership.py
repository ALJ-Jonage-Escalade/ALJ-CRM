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


# Insurance options of the form, as the members base names them (purchase_options.option_name)
INSURANCE_OPTIONS = (
    "Assurance Base", "Assurance Base +", "Assurance Base ++",
    "Assurance Option ski de piste", "Assurance Option VTT", "Assurance Option Trail",
)
# Birth date field of the flat format (schema_v2.DOB_COLUMN)
BIRTH_DATE_FIELD = "champ_Date de naissance de l'adhérent"


def insurance_of(option_name: str) -> Optional[str]:
    """The insurance of INSURANCE_OPTIONS a HelloAsso option is, None for another option."""
    lowered = option_name.lower()
    if "assurance base ++" in lowered:
        return "Assurance Base ++"
    if "assurance base +" in lowered:
        return "Assurance Base +"
    if "assurance base" in lowered:
        return "Assurance Base"
    for keyword, insurance in (("ski de piste", "Assurance Option ski de piste"), ("vtt", "Assurance Option VTT"),
                               ("trail", "Assurance Option Trail")):
        if keyword in lowered:
            return insurance
    return None


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
    payment_date: str = ""  # first payment made (instalments: the first one), "" when none
    refund_date: str = ""  # refunded (status Refunded / Refunding): when the refund was started
    options: Dict[str, float] = field(default_factory=dict)  # insurance option name -> amount in euros
    custom_fields: Dict[str, str] = field(default_factory=dict)

    def insurance(self) -> Dict[str, float]:
        """Amount of each insurance of the club's list (INSURANCE_OPTIONS) the registration took."""
        taken: Dict[str, float] = {}
        for option_name, amount in self.options.items():
            insurance = insurance_of(option_name)
            if insurance:
                taken[insurance] = amount
        return taken

    def legacy_fields(self) -> Dict[str, Any]:  # Any: text fields and amounts
        """The registration in the flat format of the former HelloAsso exports (`champ_*`, `opt_*`), read by the
        member writers (infrastructure/sqlite/schema_v2.py) and the membership dashboard."""
        fields: Dict[str, Any] = {f"champ_{name}": value for name, value in self.custom_fields.items()}  # Any: as above
        fields.update({
            "order_ref": self.order_ref,
            "order_date": self.order_date,
            "status": self.status,
            "tarif_name": self.tarif_name,
            "amount": self.amount,
            "user_lastName": self.last_name,
            "user_firstName": self.first_name,
            "payer_lastName": self.payer_last_name,
            "payer_firstName": self.payer_first_name,
            "payer_email": self.payer_email,
            BIRTH_DATE_FIELD: self.birth_date or self.birth_date_raw,
        })
        taken = self.insurance()
        for insurance in INSURANCE_OPTIONS:
            fields[f"opt_{insurance}"] = "Oui" if insurance in taken else "Non"
            fields[f"opt_Montant {insurance}"] = taken.get(insurance, 0.0)
        return fields


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


# Payment states (HelloAsso v5 PaymentState): a refund is recorded on the payments, never in the item state
_REFUND_STATES = ("Refunded", "Refunding")
_COUNTING_PAYMENT_STATES = ("Authorized", "Registered")
_UNPAID_STATES = ("Pending", "Refused", "Canceled", "Abandoned", "Error", "Init", "WaitingAuthentication")
# Item states of a valid registration, the only ones a refund on its payments replaces
_PAID_ITEM_STATES = ("Processed", "Registered", "")


def _meta_date(entity: Mapping[str, Any], key: str) -> str:  # Any: raw HelloAsso JSON
    return str((entity.get("meta") or {}).get(key) or "").strip()


def _refund(payments: list[Mapping[str, Any]]) -> tuple[str, str]:  # Any: raw HelloAsso JSON
    """(payment state, date) of the refund of a registration whose payments are all refunded or being refunded,
    ("", "") while a payment still counts. Date: the latest refund operation started, else the latest payment update."""
    refunded = [payment for payment in payments if payment.get("state") in _REFUND_STATES]
    if not refunded or any(payment.get("state") in _COUNTING_PAYMENT_STATES for payment in payments):
        return "", ""
    state = "Refunding" if any(payment.get("state") == "Refunding" for payment in refunded) else "Refunded"
    started = [_meta_date(operation, "createdAt") for payment in refunded for operation in payment.get("refundOperations") or []]
    dates = [date for date in started if date] or [date for date in (_meta_date(payment, "updatedAt") for payment in refunded) if date]
    return state, max(dates, default="")


def _payment_date(payments: list[Mapping[str, Any]]) -> str:  # Any: raw HelloAsso JSON
    made = [str(payment.get("date") or "").strip() for payment in payments if payment.get("state") not in _UNPAID_STATES]
    return min((date for date in made if date), default="")


def map_membership_item(item: Mapping[str, Any]) -> MembershipRecord:  # Any: raw HelloAsso JSON
    order = item.get("order") or {}
    user = item.get("user") or {}
    payer = item.get("payer") or {}
    custom_fields = {str(f.get("name") or ""): _custom_value(f) for f in item.get("customFields") or []}
    birth_date_raw = _field_by_words(custom_fields, "naissance")
    payments = [payment for payment in item.get("payments") or [] if isinstance(payment, Mapping)]
    status = str(item.get("state") or "").strip()
    refund_state, refund_date = _refund(payments) if status in _PAID_ITEM_STATES else ("", "")
    return MembershipRecord(
        item_id=int(item.get("id") or 0),
        order_ref=str(order.get("id") or "").strip(),
        order_date=str(order.get("date") or "").strip(),
        status=refund_state or status,
        tarif_name=str(item.get("name") or "").strip(),
        amount=(item.get("amount") or 0) / 100,
        last_name=str(user.get("lastName") or "").strip(),
        first_name=str(user.get("firstName") or "").strip(),
        payer_last_name=str(payer.get("lastName") or "").strip(),
        payer_first_name=str(payer.get("firstName") or "").strip(),
        payer_email=str(payer.get("email") or "").strip(),
        birth_date=parse_birth_date(birth_date_raw),
        birth_date_raw=birth_date_raw,
        payment_date=_payment_date(payments),
        refund_date=refund_date,
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
# Campaign (services.members.helloasso_import) and season guard
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
