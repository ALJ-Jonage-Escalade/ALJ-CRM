"""Bodies of the Google connection, server cache and HelloAsso campaign routes (Paramètres page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from api.request_body import RequestBody


class GoogleStatus(BaseModel):
    """connected: the token works; expired: a token is stored but Google refuses it; disconnected: no token."""
    status: Literal["connected", "expired", "disconnected"]
    valid: bool
    configured: bool
    client_id_configured: bool
    refresh_token_present: bool
    user_email: Optional[str]
    db_accessible: bool
    error: str


class ServiceCheck(BaseModel):
    ok: bool
    message: str


class GoogleChecks(BaseModel):
    oauth_token: ServiceCheck
    database: ServiceCheck
    gmail: ServiceCheck


class GoogleTest(BaseModel):
    """error: no access token (the other checks are skipped); warning: some check failed."""
    status: Literal["success", "warning", "error"]
    all_ok: bool
    results: GoogleChecks


class GoogleTokenUpdate(RequestBody):
    refresh_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    user_email: str = ""


class GoogleTokenUpdated(BaseModel):
    status: Literal["success"]
    message: str
    user_email: str


class GoogleLoginStart(RequestBody):
    """return_to: page of this site to come back to after Google's consent screen."""
    return_to: str = "/bureau/parametres"


class GoogleLoginUrl(BaseModel):
    """url: Google's consent page, to open in the browser; it carries a signed state valid for 10 minutes."""
    status: Literal["success"]
    url: str


class CloudDbStatus(BaseModel):
    status: Literal["success"]
    enabled: bool
    db_exists: bool
    db_filename: str
    db_size_kb: float
    member_count: int
    pending: int
    last_error: str
    # Unix time of the last sync; 0 or null before the first one
    last_sync: Optional[float]


class SyncCounters(BaseModel):
    pulled: int
    pushed: int
    full: bool


class CloudDbSync(BaseModel):
    """skipped: the server does not run on Firestore (no cache to sync)."""
    status: Literal["success", "skipped"]
    message: str
    result: Optional[SyncCounters] = None


class HelloAssoCampaignRef(BaseModel):
    """An active campaign, as saved in the app settings."""
    form_type: str
    slug: str


class HelloAssoCampaignChoice(RequestBody):
    """Campaign chosen in Paramètres › Campagne HelloAsso: form_type must be the type of the kind
    (Membership for membership, Event for competitions)."""
    form_type: str
    slug: str


class HelloAssoCampaign(BaseModel):
    """A HelloAsso form (campaign). Dates as HelloAsso gives them (ISO 8601), null when not set."""
    form_type: str
    slug: str
    title: str
    private_title: str
    state: str = Field(description="Public, Private, Draft, Disabled or Deleted; empty when not found on HelloAsso")
    activity_type: str = Field(description="HelloAsso activity of an Event form (\"Compétition\"…), empty when not given")
    url: str
    start_date: Optional[str]
    end_date: Optional[str]
    created_at: Optional[str]
    active: bool
    warning: Optional[str] = Field(description="Why the active campaign no longer matches the list (disabled, not found…)")


class HelloAssoCampaignKind(BaseModel):
    """configured: false when no campaign was chosen and the default is in use (membership: the CAMPAIGN_SLUG
    variable or the seasonal slug)."""
    active: Optional[HelloAssoCampaignRef]
    configured: bool
    campaigns: List[HelloAssoCampaign]


class HelloAssoCampaigns(BaseModel):
    """competitions: Event forms of the "Compétition" activity; others: the other Event forms, for information.
    error: HelloAsso unreachable (HTTP 200): the active campaigns are given, the lists are empty.
    warning: the activity of some Event forms could not be read (they are listed in others)."""
    membership: HelloAssoCampaignKind
    competitions: HelloAssoCampaignKind
    others: List[HelloAssoCampaign]
    error: Optional[str]
    warning: Optional[str]
