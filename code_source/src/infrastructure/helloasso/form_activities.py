"""Activity type of the club's Event forms ("Compétition", "Fête"…), for Paramètres › Campagne HelloAsso.

The forms list (`GET /organizations/{org}/forms`) does not give it: it is read from each form's details
(`/forms/Event/{slug}/public`), a few calls in parallel, and kept in memory per form for CACHE_SECONDS. A form's
activity practically never changes, and a new form is not cached yet, so it is read at once. A failed read is not
cached: the next page load tries again. Dev mode: no cache (as the access roles).
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

from infrastructure import runtime_env
from infrastructure.helloasso import api as helloasso_api
from infrastructure.timed_cache import TimedCache

logger = logging.getLogger("alj")

CACHE_SECONDS = 24 * 3600
# Details read at the same time (a handful of Event forms; stays polite with HelloAsso)
MAX_PARALLEL_READS = 4

FormKey = Tuple[str, str]  # (form type, slug)
# Any: HelloAsso JSON (FormPublicModel)
FetchDetails = Callable[[str, str, str], Dict[str, Any]]


class Activity(TypedDict):
    activityType: Optional[str]
    activityTypeId: Optional[int]


ActivityCache = TimedCache[FormKey, Activity]

_current: Optional[ActivityCache] = None
_current_lock = threading.Lock()


def current() -> ActivityCache:
    """The server's cache (created on first use; no cache in dev mode)."""
    global _current
    with _current_lock:
        if _current is None:
            _current = ActivityCache(0 if runtime_env.is_dev() else CACHE_SECONDS)
        return _current


def install(cache: Optional[ActivityCache]) -> None:
    """Replaces the server's cache (tests); None: a new one on next use."""
    global _current
    with _current_lock:
        _current = cache


def _key(form: Dict[str, Any]) -> FormKey:  # Any: HelloAsso JSON
    return str(form.get("formType") or ""), str(form.get("formSlug") or "")


def _activity_of(details: Dict[str, Any]) -> Activity:  # Any: HelloAsso JSON
    type_id = details.get("activityTypeId")
    return {"activityType": details.get("activityType") or None, "activityTypeId": type_id if isinstance(type_id, int) else None}


def with_activities(forms: List[Dict[str, Any]], token: str,  # Any: HelloAsso JSON
                    fetch: Optional[FetchDetails] = None,
                    cache: Optional[ActivityCache] = None) -> Tuple[List[Dict[str, Any]], int]:  # Any: HelloAsso JSON
    """The forms, Event ones completed with `activityType` / `activityTypeId`, and the number of Event forms whose
    details could not be read (left without activity). A form that already has `activityTypeId` is kept as is."""
    fetch = fetch or helloasso_api.get_public_form
    cache = cache or current()
    keys = sorted({_key(form) for form in forms
                   if form.get("formType") == "Event" and form.get("formSlug") and form.get("activityTypeId") is None})
    activities: Dict[FormKey, Activity] = {}

    def read(key: FormKey) -> Optional[Activity]:
        try:
            return cache.get_or_load(key, lambda: _activity_of(fetch(key[0], key[1], token)))
        except Exception as e:  # HelloAssoApiError or an unexpected answer: this form only, counted as unread
            logger.warning("Activité du formulaire HelloAsso %s/%s illisible : %s", key[0], key[1], e)
            return None

    failed = 0
    if keys:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_READS) as pool:
            for key, activity in zip(keys, pool.map(read, keys), strict=True):
                if activity is None:
                    failed += 1
                else:
                    activities[key] = activity
    return [{**form, **activities[_key(form)]} if _key(form) in activities else form for form in forms], failed
