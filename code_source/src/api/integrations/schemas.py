"""Bodies of the Google connection and server cache routes (Paramètres page of the Vue app).

The response models are the API contract: the frontend's TypeScript types are generated from them
(dev/export_openapi.py, then `npm run gen:api` in frontend/)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from api.request_body import RequestBody


class GoogleStatus(BaseModel):
    """connected: the token works; expired: a token is stored but Google refuses it; disconnected: no token."""
    status: Literal["connected", "expired", "disconnected"]
    valid: bool
    configured: bool
    client_id_configured: bool
    refresh_token_present: bool
    user_email: Optional[str]
    backend: str
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
