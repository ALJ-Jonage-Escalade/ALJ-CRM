"""Paramètres › Campagne HelloAsso: the club's HelloAsso campaigns and the active one of each kind.

GET: coaches and above (public HelloAsso data); always 200, `error` set when HelloAsso can't be read (the active
campaigns come from the app settings and are still given). PUT: admins only (api_auth.required_role); checks the
shape of the choice, not that the campaign exists on HelloAsso (the page lists it from there).
Firestore only (server.py FIRESTORE_ONLY_PATHS): never waits for the SQLite cache.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from api.integrations.schemas import HelloAssoCampaignChoice, HelloAssoCampaignRef, HelloAssoCampaigns
from api.members.dashboard import get_target_slug
from api.responses import error_responses, internal_error
from domain import helloasso_campaigns as campaigns
from domain.helloasso_campaigns import CampaignKind, CampaignRef
from infrastructure.firestore.app_settings import (
    HELLOASSO_COMPETITION_CAMPAIGN, HELLOASSO_MEMBERSHIP_CAMPAIGN, AppSettingsRepository,
)
from infrastructure.firestore.client import FirestoreError
from infrastructure.helloasso import api as helloasso_api
from services.errors import InvalidRequest, StorageUnavailable

logger = logging.getLogger("alj")

router = APIRouter(prefix="/api/helloasso/campaigns")

SETTING_OF_KIND: Dict[str, str] = {"membership": HELLOASSO_MEMBERSHIP_CAMPAIGN, "competitions": HELLOASSO_COMPETITION_CAMPAIGN}

CREDENTIALS_MISSING = "Identifiants API HelloAsso non configurés sur le serveur."
HELLOASSO_UNREACHABLE = "Impossible de lire les campagnes sur HelloAsso pour le moment. Réessayez dans un instant."
SETTINGS_UNAVAILABLE = "Réglages indisponibles (base Firestore injoignable), réessayez dans un instant."


def _setting(kind: str) -> str:
    try:
        return AppSettingsRepository.get(SETTING_OF_KIND[kind]) or ""
    except FirestoreError as e:
        raise StorageUnavailable(SETTINGS_UNAVAILABLE) from e


def _active_campaign(kind: str) -> tuple[CampaignRef | None, bool]:
    """Active campaign of the kind and whether it was chosen (False: the default in use, or none)."""
    active = campaigns.parse_setting(_setting(kind), kind)
    configured = active is not None
    if active is None and kind == "membership":
        # What the dashboard uses until a campaign is chosen (CAMPAIGN_SLUG variable or seasonal slug)
        active = {"form_type": campaigns.FORM_TYPE_OF_KIND[kind], "slug": get_target_slug()}
    return active, configured


def _helloasso_forms() -> tuple[List[Dict[str, Any]], str | None]:  # Any: HelloAsso JSON
    """Membership and Event forms of the club (every state but Deleted), or the error shown by the page."""
    if not helloasso_api.credentials_configured():
        return [], CREDENTIALS_MISSING
    try:
        return helloasso_api.list_forms(campaigns.FORM_TYPE_OF_KIND.values(), campaigns.LOOKUP_STATES), None
    except Exception as e:  # HelloAssoApiError, or an unexpected answer: the active campaigns are still shown
        internal_error(e, "list_helloasso_campaigns")
        return [], HELLOASSO_UNREACHABLE


@router.get("", response_model=HelloAssoCampaigns, responses=error_responses(503))
def list_campaigns() -> Dict[str, Any]:  # Any: response body, checked by response_model
    # Settings first: they don't need HelloAsso (a Firestore failure is a 503 before HelloAsso is called)
    actives = {kind: _active_campaign(kind) for kind in SETTING_OF_KIND}
    forms, error = _helloasso_forms()
    body: Dict[str, Any] = {"error": error}  # Any: response body
    for kind, (active, configured) in actives.items():
        # No list without HelloAsso: the page shows the active campaign alone
        rows = campaigns.campaign_table(forms, kind, active) if error is None else []
        body[kind] = {"active": active, "configured": configured, "campaigns": rows}
    return body


@router.put("/{kind}", response_model=HelloAssoCampaignRef, responses=error_responses(400, 503))
def choose_campaign(kind: CampaignKind, body: HelloAssoCampaignChoice) -> CampaignRef:
    expected = campaigns.FORM_TYPE_OF_KIND[kind]
    if body.form_type != expected:
        raise InvalidRequest(f"Une campagne de type {expected} est attendue (reçu : {body.form_type or 'aucun'}).")
    if not body.slug:
        raise InvalidRequest("Aucune campagne choisie.")
    try:
        AppSettingsRepository.save(SETTING_OF_KIND[kind], campaigns.setting_value(expected, body.slug))
    except FirestoreError as e:
        raise StorageUnavailable(SETTINGS_UNAVAILABLE) from e
    logger.info("HelloAsso %s campaign set to %s", kind, body.slug)
    return {"form_type": expected, "slug": body.slug}
