"""infrastructure.helloasso.form_activities: Event forms completed from their details, cached per form."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from infrastructure.helloasso.api import HelloAssoApiError
from infrastructure.helloasso.form_activities import ActivityCache, with_activities

COMPETITION = {"activityType": "Compétition", "activityTypeId": 3}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeDetails:
    """get_public_form stand-in: each form's details, the reads made, and the slugs that fail."""

    def __init__(self, failing: tuple[str, ...] = ()) -> None:
        self.reads: List[str] = []
        self.failing = failing

    def __call__(self, form_type: str, slug: str, token: str) -> Dict[str, Any]:  # Any: HelloAsso JSON
        assert token == "token"  # noqa: S101 - the page's single token is reused
        self.reads.append(slug)
        if slug in self.failing:
            raise HelloAssoApiError("API HelloAsso : HTTP 500")
        return {"formSlug": slug, "formType": form_type, **COMPETITION}


FORMS = [{"formSlug": "comp", "formType": "Event"}, {"formSlug": "adhesion", "formType": "Membership"},
         {"formSlug": "party", "formType": "Event", "activityType": "Fête", "activityTypeId": 1}]


def test_reads_only_event_forms_without_activity() -> None:
    details = FakeDetails()
    forms, unread = with_activities(FORMS, "token", fetch=details, cache=ActivityCache(clock=FakeClock()))
    assert (details.reads, unread) == (["comp"], 0)
    assert forms == [{"formSlug": "comp", "formType": "Event", **COMPETITION}, FORMS[1], FORMS[2]]


def test_cached_until_expiry() -> None:
    clock, details = FakeClock(), FakeDetails()
    cache = ActivityCache(cache_seconds=60, clock=clock)
    with_activities(FORMS, "token", fetch=details, cache=cache)
    clock.now += 59
    forms, _ = with_activities(FORMS, "token", fetch=details, cache=cache)
    assert details.reads == ["comp"]
    assert forms[0]["activityTypeId"] == 3
    clock.now += 1
    with_activities(FORMS, "token", fetch=details, cache=cache)
    assert details.reads == ["comp", "comp"]


def test_failed_read_counted_and_not_cached() -> None:
    cache = ActivityCache(clock=FakeClock())
    forms, unread = with_activities(FORMS, "token", fetch=FakeDetails(failing=("comp",)), cache=cache)
    assert (unread, forms[0]) == (1, FORMS[0])
    details = FakeDetails()
    with_activities(FORMS, "token", fetch=details, cache=cache)
    assert details.reads == ["comp"]


@pytest.mark.parametrize("cache_seconds", [0, -1])
def test_no_cache_keeps_nothing(cache_seconds: int) -> None:
    details, cache = FakeDetails(), ActivityCache(cache_seconds=cache_seconds, clock=FakeClock())
    with_activities(FORMS, "token", fetch=details, cache=cache)
    with_activities(FORMS, "token", fetch=details, cache=cache)
    assert details.reads == ["comp", "comp"]


def test_unexpected_details_give_no_activity() -> None:
    forms, unread = with_activities(FORMS[:1], "token", fetch=lambda *_: {"activityTypeId": "3"},
                                    cache=ActivityCache(clock=FakeClock()))
    assert (unread, forms[0]["activityType"], forms[0]["activityTypeId"]) == (0, None, None)


def test_invalidate_reads_again() -> None:
    details, cache = FakeDetails(), ActivityCache(clock=FakeClock())
    with_activities(FORMS, "token", fetch=details, cache=cache)
    cache.invalidate()
    with_activities(FORMS, "token", fetch=details, cache=cache)
    assert details.reads == ["comp", "comp"]
