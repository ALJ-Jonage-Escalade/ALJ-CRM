"""HelloAsso campaigns of Paramètres › Campagne HelloAsso (pure logic, testable).

Two kinds of campaign, one active of each, saved in the Firestore `app_settings` as "FormType:slug":
- membership: the Membership form whose registrations the dashboard shows;
- competitions: the seasonal Event form that competition payments are matched against.

Input: the forms of HelloAsso's `GET /organizations/{org}/forms` (FormLightModel).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Literal, Optional, TypedDict

from domain.competitions.matching import parse_campaign_identifier

CampaignKind = Literal["membership", "competitions"]

# HelloAsso form type of each kind
FORM_TYPE_OF_KIND: Dict[str, str] = {"membership": "Membership", "competitions": "Event"}
# States listed in the tables (Draft, Disabled and Deleted forms take no payment)
LISTED_STATES = ("Public", "Private")
# Every state but Deleted: the active campaign is found even once disabled
LOOKUP_STATES = ("Public", "Private", "Draft", "Disabled")

_STATE_WARNINGS = {
    "Draft": "Campagne en brouillon sur HelloAsso",
    "Disabled": "Campagne désactivée sur HelloAsso",
    "Deleted": "Campagne supprimée sur HelloAsso",
}
NOT_FOUND_WARNING = "Campagne introuvable sur HelloAsso"


class CampaignRef(TypedDict):
    form_type: str
    slug: str


class CampaignRow(TypedDict):
    """A row of a table: the HelloAsso form, flattened. Dates as HelloAsso gives them (ISO 8601) or None."""
    form_type: str
    slug: str
    title: str
    private_title: str
    state: str
    url: str
    start_date: Optional[str]
    end_date: Optional[str]
    created_at: Optional[str]
    active: bool
    warning: Optional[str]


def parse_setting(value: Optional[str], kind: str) -> Optional[CampaignRef]:
    """Active campaign saved in a setting ("FormType:slug", or a bare slug / URL typed in the past), None when blank
    or unreadable. A bare slug takes the type of the kind."""
    raw = (value or "").strip()
    if not raw:
        return None
    if ":" not in raw:
        return {"form_type": FORM_TYPE_OF_KIND[kind], "slug": raw}
    try:
        parsed = parse_campaign_identifier(raw)
    except ValueError:
        return None
    return {"form_type": parsed["form_type"], "slug": parsed["slug"]}


def setting_value(form_type: str, slug: str) -> str:
    return f"{form_type}:{slug}"


def _text(value: Any) -> str:  # Any: a JSON value
    return str(value or "").strip()


def _optional(value: Any) -> Optional[str]:  # Any: a JSON value
    return _text(value) or None


def campaign_row(form: Dict[str, Any], active: bool = False, warning: Optional[str] = None) -> CampaignRow:  # Any: HelloAsso JSON
    return {
        "form_type": _text(form.get("formType")),
        "slug": _text(form.get("formSlug")),
        "title": _text(form.get("title")),
        "private_title": _text(form.get("privateTitle")),
        "state": _text(form.get("state")),
        "url": _text(form.get("url")),
        "start_date": _optional(form.get("startDate")),
        "end_date": _optional(form.get("endDate")),
        "created_at": _optional((form.get("meta") or {}).get("createdAt")),
        "active": active,
        "warning": warning,
    }


def _sort_key(row: CampaignRow) -> str:
    """Newest first: start date, or creation date when the form has none (membership forms may not)."""
    return row["start_date"] or row["created_at"] or ""


def active_warning(form: Optional[Dict[str, Any]], expected_form_type: str) -> Optional[str]:  # Any: HelloAsso JSON
    """Why the active campaign is not among the listed ones, or None when it is."""
    if form is None:
        return NOT_FOUND_WARNING
    form_type = _text(form.get("formType"))
    if form_type != expected_form_type:
        return f"Formulaire de type {form_type or 'inconnu'} (attendu : {expected_form_type})"
    state = _text(form.get("state"))
    if state not in LISTED_STATES:
        return _STATE_WARNINGS.get(state, f"Campagne à l'état {state or 'inconnu'} sur HelloAsso")
    return None


def campaign_table(forms: Iterable[Dict[str, Any]], kind: str, active: Optional[CampaignRef]) -> List[CampaignRow]:  # Any: HelloAsso JSON
    """Rows of a kind's table: its Public / Private forms, newest first, and the active campaign always, flagged with
    a warning when it no longer matches (other type, disabled, not found). `forms` may hold every type and state."""
    form_type = FORM_TYPE_OF_KIND[kind]
    all_forms = list(forms)
    active_slug = active["slug"] if active else None
    rows = [campaign_row(form, active=_text(form.get("formSlug")) == active_slug)
            for form in all_forms
            if _text(form.get("formType")) == form_type and _text(form.get("state")) in LISTED_STATES]
    if active and not any(row["active"] for row in rows):
        active_form = next((form for form in all_forms if _text(form.get("formSlug")) == active_slug), None)
        if active_form is None:
            rows.append({**campaign_row({"formType": active["form_type"], "formSlug": active_slug}), "active": True,
                         "warning": NOT_FOUND_WARNING})
        else:
            rows.append(campaign_row(active_form, active=True, warning=active_warning(active_form, form_type)))
    return sorted(rows, key=_sort_key, reverse=True)
