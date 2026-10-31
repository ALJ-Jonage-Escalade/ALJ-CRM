"""Activity type of the club's Event forms ("Compétition", "Fête"…), for Paramètres › Campagne HelloAsso.

The forms list (`GET /organizations/{org}/forms`) does not give it: it is read from each form's details
(`/forms/Event/{slug}/public`), a few calls in parallel, and kept in memory per form for CACHE_SECONDS. A form's
activity practically never changes, and a new form is not cached yet, so it is read at once. A failed read is not
cached: the next page load tries again. Dev mode: no cache (as the access roles).

Cache of this feature only, until the server has a shared one (issue #82).
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, TypedDict

from infrastructure import runtime_env
from infrastructure.helloasso import api as helloasso_api

logger = logging.getLogger("alj")

CACHE_SECONDS = 24 * 3600
# Details read at the same time (a handful of Event forms; stays polite with HelloAsso)
MAX_PARALLEL_READS = 4

Clock = Callable[[], float]
FormKey = Tuple[str, str]  # (form type, slug)
# Any: HelloAsso JSON (FormPublicModel)
FetchDetails = Callable[[str, str, str], Dict[str, Any]]


class Activity(TypedDict):
    activityType: Optional[str]
    activityTypeId: Optional[int]


class ActivityCache:
    """Activity of each form, at most `cache_seconds` old (0: nothing kept)."""

    def __init__(self, cache_seconds: float = CACHE_SECONDS, clock: Clock = time.monotonic) -> None:
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: Dict[FormKey, Tuple[float, Activity]] = {}

    def get(self, key: FormKey) -> Optional[Activity]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            saved_at, activity = entry
            if self._clock() - saved_at >= self._cache_seconds:
                del self._entries[key]
                return None
            return activity

    def put(self, key: FormKey, activity: Activity) -> None:
        if self._cache_seconds <= 0:
            return
        with self._lock:
            self._entries[key] = (self._clock(), activity)

    def invalidate(self) -> None:
        with self._lock:
            self._entries.clear()


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
    keys = {_key(form) for form in forms
            if form.get("formType") == "Event" and form.get("formSlug") and form.get("activityTypeId") is None}
    activities: Dict[FormKey, Activity] = {}
    to_read: List[FormKey] = []
    for key in sorted(keys):
        cached = cache.get(key)
        if cached is None:
            to_read.append(key)
        else:
            activities[key] = cached

    def read(key: FormKey) -> Optional[Activity]:
        try:
            return _activity_of(fetch(key[0], key[1], token))
        except Exception as e:  # HelloAssoApiError or an unexpected answer: this form only, counted as unread
            logger.warning("Activité du formulaire HelloAsso %s/%s illisible : %s", key[0], key[1], e)
            return None

    failed = 0
    if to_read:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_READS) as pool:
            for key, activity in zip(to_read, pool.map(read, to_read), strict=True):
                if activity is None:
                    failed += 1
                else:
                    activities[key] = activity
                    cache.put(key, activity)
    return [{**form, **activities[_key(form)]} if _key(form) in activities else form for form in forms], failed
