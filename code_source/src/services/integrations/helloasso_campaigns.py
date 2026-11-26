"""Paramètres › Campagne HelloAsso: the club's HelloAsso campaigns and the active one of each kind (app settings).

The listing never fails because of HelloAsso: `error` is set and the active campaigns, read from the settings, are
still given. The choice checks the shape of the campaign, not that it exists on HelloAsso (the page lists it from there).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from domain import helloasso_campaigns as campaigns
from domain.errors import InvalidRequest, StorageUnavailable
from domain.helloasso_campaigns import CampaignKind, CampaignRef, CampaignRow
from infrastructure.firestore.app_settings import (
    HELLOASSO_COMPETITION_CAMPAIGN, HELLOASSO_MEMBERSHIP_CAMPAIGN, AppSettingsRepository,
)
from infrastructure.firestore.client import FirestoreError
from infrastructure.helloasso import api as helloasso_api
from infrastructure.helloasso import form_activities
from services.members.helloasso_import import MembershipImportService

logger = logging.getLogger("alj")

SETTING_OF_KIND: Dict[CampaignKind, str] = {"membership": HELLOASSO_MEMBERSHIP_CAMPAIGN, "competitions": HELLOASSO_COMPETITION_CAMPAIGN}

CREDENTIALS_MISSING = "Identifiants API HelloAsso non configurés sur le serveur."
HELLOASSO_UNREACHABLE = "Impossible de lire les campagnes sur HelloAsso pour le moment. Réessayez dans un instant."
SETTINGS_UNAVAILABLE = "Réglages indisponibles (base Firestore injoignable), réessayez dans un instant."


class KindCampaigns(TypedDict):
    """active: the chosen campaign, else the default the import uses (membership), else None; configured: chosen."""
    active: Optional[CampaignRef]
    configured: bool
    campaigns: List[CampaignRow]


class CampaignListing(TypedDict):
    """error: HelloAsso unreachable (the lists are empty); warning: some Event activities unread (listed in others)."""
    membership: KindCampaigns
    competitions: KindCampaigns
    others: List[CampaignRow]
    error: Optional[str]
    warning: Optional[str]


def _setting(kind: CampaignKind) -> str:
    try:
        return AppSettingsRepository.get(SETTING_OF_KIND[kind]) or ""
    except FirestoreError as e:
        raise StorageUnavailable(SETTINGS_UNAVAILABLE) from e


def _active_campaign(kind: CampaignKind) -> tuple[CampaignRef | None, bool]:
    """Active campaign of the kind and whether it was chosen (False: the default in use, or none)."""
    active = campaigns.parse_setting(_setting(kind), kind)
    configured = active is not None
    if active is None and kind == "membership":
        # What the members import uses until a campaign is chosen (CAMPAIGN_SLUG variable or seasonal slug)
        active = {"form_type": campaigns.FORM_TYPE_OF_KIND[kind], "slug": MembershipImportService.campaign_slug()}
    return active, configured


def activities_unread(count: int) -> str:
    return (f"Activité de {count} formulaire(s) illisible sur HelloAsso pour le moment : classé(s) dans « Autres ». "
            "Actualisez dans un instant.")


def _helloasso_forms() -> tuple[List[Dict[str, Any]], str | None, str | None]:  # Any: HelloAsso JSON
    """Membership and Event forms of the club (every state but Deleted), Event ones with their activity (one token
    for every call), then the error shown by the page and the warning when some activities could not be read."""
    if not helloasso_api.credentials_configured():
        return [], CREDENTIALS_MISSING, None
    try:
        token = helloasso_api.require_access_token()
        forms = helloasso_api.list_forms(campaigns.FORM_TYPE_OF_KIND.values(), campaigns.LOOKUP_STATES, token=token)
    except Exception:  # HelloAssoApiError, or an unexpected answer: the active campaigns are still shown
        logger.exception("[list_helloasso_campaigns] HelloAsso campaigns unreadable")
        return [], HELLOASSO_UNREACHABLE, None
    forms, unread = form_activities.with_activities(forms, token)
    return forms, None, activities_unread(unread) if unread else None


def list_campaigns() -> CampaignListing:
    # Settings first: they don't need HelloAsso (a Firestore failure is a StorageUnavailable before HelloAsso is called)
    membership, competitions = _active_campaign("membership"), _active_campaign("competitions")
    forms, error, warning = _helloasso_forms()

    def of_kind(kind: CampaignKind, active: Optional[CampaignRef], configured: bool) -> KindCampaigns:
        # No list without HelloAsso: the page shows the active campaign alone
        rows = campaigns.campaign_table(forms, kind, active) if error is None else []
        return {"active": active, "configured": configured, "campaigns": rows}

    return {"membership": of_kind("membership", *membership), "competitions": of_kind("competitions", *competitions),
            "others": campaigns.other_events_table(forms), "error": error, "warning": warning}


def choose_campaign(kind: CampaignKind, form_type: str, slug: str) -> CampaignRef:
    """Makes this campaign the active one of the kind."""
    expected = campaigns.FORM_TYPE_OF_KIND[kind]
    if form_type != expected:
        raise InvalidRequest(f"Une campagne de type {expected} est attendue (reçu : {form_type or 'aucun'}).")
    if not slug:
        raise InvalidRequest("Aucune campagne choisie.")
    try:
        AppSettingsRepository.save(SETTING_OF_KIND[kind], campaigns.setting_value(expected, slug))
    except FirestoreError as e:
        raise StorageUnavailable(SETTINGS_UNAVAILABLE) from e
    logger.info("HelloAsso %s campaign set to %s", kind, slug)
    return {"form_type": expected, "slug": slug}
