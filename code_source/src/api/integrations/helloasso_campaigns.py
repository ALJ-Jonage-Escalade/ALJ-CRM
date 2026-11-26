"""Paramètres › Campagne HelloAsso: the club's HelloAsso campaigns and the active one of each kind.

GET: coaches and above (public HelloAsso data); always 200, `error` set when HelloAsso can't be read (the active
campaigns come from the app settings and are still given). PUT: admins only (api_auth.required_role).
Firestore only (server.py FIRESTORE_ONLY_PATHS): never waits for the SQLite cache.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.integrations.schemas import HelloAssoCampaignChoice, HelloAssoCampaignRef, HelloAssoCampaigns
from api.responses import error_responses
from domain.helloasso_campaigns import CampaignKind, CampaignRef
from services.integrations import helloasso_campaigns
from services.integrations.helloasso_campaigns import CampaignListing

router = APIRouter(prefix="/api/helloasso/campaigns")


@router.get("", response_model=HelloAssoCampaigns, responses=error_responses(503))
def list_campaigns() -> CampaignListing:
    return helloasso_campaigns.list_campaigns()


@router.put("/{kind}", response_model=HelloAssoCampaignRef, responses=error_responses(400, 503))
def choose_campaign(kind: CampaignKind, body: HelloAssoCampaignChoice) -> CampaignRef:
    return helloasso_campaigns.choose_campaign(kind, body.form_type, body.slug)
