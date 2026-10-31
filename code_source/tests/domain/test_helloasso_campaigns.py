"""Tables of Paramètres › Campagne HelloAsso: filter, sort, active campaign always listed."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from domain.helloasso_campaigns import NOT_FOUND_WARNING, campaign_table, other_events_table, parse_setting


def form(slug: str, form_type: str = "Event", state: str = "Public", start: Optional[str] = None,
         created: Optional[str] = None, **extra: Any) -> Dict[str, Any]:  # Any: HelloAsso JSON
    """A HelloAsso form; an Event one is a "Compétition" unless `activityTypeId` says otherwise."""
    activity = {"activityType": "Compétition", "activityTypeId": 3} if form_type == "Event" else {}
    return {"formSlug": slug, "formType": form_type, "state": state, "title": slug.title(), "startDate": start,
            "meta": {"createdAt": created} if created else {}, **activity, **extra}


def party(slug: str, **extra: Any) -> Dict[str, Any]:  # Any: HelloAsso JSON
    return form(slug, activityType="Fête", activityTypeId=1, **extra)


def test_campaign_table_keeps_the_kind_and_listed_states() -> None:
    forms = [form("comp-public"), form("comp-private", state="Private"), form("comp-draft", state="Draft"),
             form("comp-disabled", state="Disabled"), form("adhesion", form_type="Membership")]
    assert [row["slug"] for row in campaign_table(forms, "competitions", None)] == ["comp-public", "comp-private", "comp-draft"]
    assert [row["slug"] for row in campaign_table(forms, "membership", None)] == ["adhesion"]


def test_competitions_only_of_the_competition_activity_others_apart() -> None:
    forms = [form("comp"), party("soiree", start="2026-12-12T19:00:00+01:00"), form("unknown", activityTypeId=None),
             party("old-party", state="Disabled"), form("adhesion", form_type="Membership")]
    assert [row["slug"] for row in campaign_table(forms, "competitions", None)] == ["comp"]
    others = other_events_table(forms)
    assert [(row["slug"], row["activity_type"], row["active"]) for row in others] == [
        ("soiree", "Fête", False), ("unknown", "Compétition", False)]


def test_campaign_table_sorted_by_state_then_start_date_then_title() -> None:
    forms = [form("draft", state="Draft", start="2027-09-01T00:00:00+02:00"),
             form("private-new", state="Private", start="2026-09-01T00:00:00+02:00"),
             form("public-undated-b", title="Équipe B"),
             form("public-old", start="2024-09-01T00:00:00+02:00"),
             form("public-undated-a", title="équipe a"),
             form("public-new", start="2026-09-01T10:00:00+02:00"),
             form("public-new-utc", start="2026-09-01T07:00:00+00:00"),  # 09:00 in Paris: before public-new
             form("disabled", state="Disabled", start="2028-01-01T00:00:00+01:00")]
    active = {"form_type": "Event", "slug": "disabled"}
    assert [row["slug"] for row in campaign_table(forms, "competitions", active)] == [
        "public-new", "public-new-utc", "public-old", "public-undated-a", "public-undated-b", "private-new", "draft", "disabled"]


def test_campaign_row_fields() -> None:
    forms = [form("comp", start="2026-09-01T00:00:00+02:00", endDate="2027-06-30T23:59:00+02:00", privateTitle="Interne",
                  url="https://www.helloasso.com/associations/club/evenements/comp", created="2026-08-01T09:00:00+02:00")]
    row = campaign_table(forms, "competitions", {"form_type": "Event", "slug": "comp"})[0]
    assert row == {"form_type": "Event", "slug": "comp", "title": "Comp", "private_title": "Interne", "state": "Public",
                   "activity_type": "Compétition",
                   "url": "https://www.helloasso.com/associations/club/evenements/comp",
                   "start_date": "2026-09-01T00:00:00+02:00", "end_date": "2027-06-30T23:59:00+02:00",
                   "created_at": "2026-08-01T09:00:00+02:00", "active": True, "warning": None}


@pytest.mark.parametrize("forms, warning", [
    ([form("comp", state="Disabled")], "Campagne désactivée sur HelloAsso"),
    ([form("comp", form_type="Membership")], "Formulaire de type Membership (attendu : Event)"),
    ([party("comp")], "Activité « Fête » (attendue : Compétition)"),
    ([form("comp", activityType=None, activityTypeId=None)], "Activité « non renseignée » (attendue : Compétition)"),
    ([], NOT_FOUND_WARNING),
])
def test_active_campaign_listed_with_a_warning(forms: list, warning: str) -> None:
    rows = campaign_table([*forms, form("other")], "competitions", {"form_type": "Event", "slug": "comp"})
    active = [row for row in rows if row["active"]]
    assert [(row["slug"], row["warning"]) for row in active] == [("comp", warning)]
    assert "other" in [row["slug"] for row in rows]


def test_active_draft_campaign_listed_without_warning() -> None:
    rows = campaign_table([form("comp", state="Draft")], "competitions", {"form_type": "Event", "slug": "comp"})
    assert [(row["slug"], row["state"], row["active"], row["warning"]) for row in rows] == [("comp", "Draft", True, None)]


@pytest.mark.parametrize("value, kind, expected", [
    ("Membership:adhesion-2026", "membership", {"form_type": "Membership", "slug": "adhesion-2026"}),
    ("adhesion-2026", "membership", {"form_type": "Membership", "slug": "adhesion-2026"}),
    ("competitions-2026", "competitions", {"form_type": "Event", "slug": "competitions-2026"}),
    ("https://www.helloasso.com/associations/club/evenements/comp", "competitions", {"form_type": "Event", "slug": "comp"}),
    ("https://www.helloasso.com/associations/club/inconnu/comp", "competitions", None),
    ("  ", "competitions", None),
    (None, "membership", None),
])
def test_parse_setting(value: Optional[str], kind: str, expected: Optional[dict]) -> None:
    assert parse_setting(value, kind) == expected
