"""HelloAsso campaigns of Paramètres › Campagne HelloAsso (pure logic, testable).

Two kinds of campaign, one active of each, saved in the Firestore `app_settings` as "FormType:slug":
- membership: the Membership form whose registrations the dashboard shows;
- competitions: the seasonal Event form that competition payments are matched against.
The other Event forms (parties, trips…) are listed apart, for information ("Autres").

Input: the forms of HelloAsso's `GET /organizations/{org}/forms` (FormLightModel).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Literal, Optional, TypedDict

from domain.competitions.matching import parse_campaign_identifier
from domain.utils import normalize_string

CampaignKind = Literal["membership", "competitions"]

# HelloAsso form type of each kind
FORM_TYPE_OF_KIND: Dict[str, str] = {"membership": "Membership", "competitions": "Event"}
# States listed in the tables: drafts too, so next season's form can be chosen before it opens
# (Disabled and Deleted forms take no payment)
LISTED_STATES = ("Public", "Private", "Draft")
# Every state but Deleted: the active campaign is found even once disabled
LOOKUP_STATES = ("Public", "Private", "Draft", "Disabled")
# HelloAsso activity "Compétition" of the Event forms (GET /values/form/Event/types). `activityTypeId` is returned by the
# forms list but not documented there: a form without it is not taken as a competitions campaign.
COMPETITION_ACTIVITY_TYPE_ID = 3

_STATE_WARNINGS = {
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
    activity_type: str
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
        "activity_type": _text(form.get("activityType")),
        "url": _text(form.get("url")),
        "start_date": _optional(form.get("startDate")),
        "end_date": _optional(form.get("endDate")),
        "created_at": _optional((form.get("meta") or {}).get("createdAt")),
        "active": active,
        "warning": warning,
    }


# Order of the states in a table; the others (Disabled, Deleted, not found: an active campaign only) come last
_STATE_ORDER = {"Public": 0, "Private": 1, "Draft": 2}


def _start_timestamp(row: CampaignRow) -> Optional[float]:
    try:
        return datetime.fromisoformat(row["start_date"]).timestamp() if row["start_date"] else None
    except ValueError:
        return None


def _sort_key(row: CampaignRow) -> tuple[int, int, float, str]:
    """State (Public, Private, Draft, then the others), then start date, newest first (forms without one after),
    then title in alphabetical order (case and accents ignored)."""
    start = _start_timestamp(row)
    return (_STATE_ORDER.get(row["state"], len(_STATE_ORDER)), start is None, -(start or 0.0),
            normalize_string(row["title"] or row["slug"]))


def _is_competition(form: Dict[str, Any]) -> bool:  # Any: HelloAsso JSON
    return form.get("activityTypeId") == COMPETITION_ACTIVITY_TYPE_ID


def _of_kind(form: Dict[str, Any], kind: str) -> bool:  # Any: HelloAsso JSON
    """Form of the kind's type, and for competitions of the "Compétition" activity."""
    return _text(form.get("formType")) == FORM_TYPE_OF_KIND[kind] and (kind != "competitions" or _is_competition(form))


def _listed(form: Dict[str, Any]) -> bool:  # Any: HelloAsso JSON
    return _text(form.get("state")) in LISTED_STATES


def active_warning(form: Optional[Dict[str, Any]], kind: str) -> Optional[str]:  # Any: HelloAsso JSON
    """Why the active campaign is not among the listed ones, or None when it is."""
    if form is None:
        return NOT_FOUND_WARNING
    form_type = _text(form.get("formType"))
    expected_form_type = FORM_TYPE_OF_KIND[kind]
    if form_type != expected_form_type:
        return f"Formulaire de type {form_type or 'inconnu'} (attendu : {expected_form_type})"
    if kind == "competitions" and not _is_competition(form):
        return f"Activité « {_text(form.get('activityType')) or 'non renseignée'} » (attendue : Compétition)"
    state = _text(form.get("state"))
    if state not in LISTED_STATES:
        return _STATE_WARNINGS.get(state, f"Campagne à l'état {state or 'inconnu'} sur HelloAsso")
    return None


def campaign_table(forms: Iterable[Dict[str, Any]], kind: str, active: Optional[CampaignRef]) -> List[CampaignRow]:  # Any: HelloAsso JSON
    """Rows of a kind's table: its Public / Private / Draft forms (order: _sort_key), and the active campaign always, flagged
    with a warning when it no longer matches (other type or activity, disabled, not found). `forms` may hold every type
    and state."""
    all_forms = list(forms)
    active_slug = active["slug"] if active else None
    rows = [campaign_row(form, active=_text(form.get("formSlug")) == active_slug)
            for form in all_forms
            if _of_kind(form, kind) and _listed(form)]
    if active and not any(row["active"] for row in rows):
        active_form = next((form for form in all_forms if _text(form.get("formSlug")) == active_slug), None)
        if active_form is None:
            rows.append({**campaign_row({"formType": active["form_type"], "formSlug": active_slug}), "active": True,
                         "warning": NOT_FOUND_WARNING})
        else:
            rows.append(campaign_row(active_form, active=True, warning=active_warning(active_form, kind)))
    return sorted(rows, key=_sort_key)


def other_events_table(forms: Iterable[Dict[str, Any]]) -> List[CampaignRow]:  # Any: HelloAsso JSON
    """Rows of the "Autres" table: the Public / Private / Draft Event forms of another activity than "Compétition"
    (order: _sort_key). Nothing to choose there: `active` is always False."""
    rows = [campaign_row(form) for form in forms
            if _text(form.get("formType")) == "Event" and not _is_competition(form) and _listed(form)]
    return sorted(rows, key=_sort_key)
