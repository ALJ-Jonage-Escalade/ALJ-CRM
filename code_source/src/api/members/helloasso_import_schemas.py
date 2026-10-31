"""Bodies of the HelloAsso membership import routes (api/members/helloasso_import.py), API contract of the Vue app."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

from api.request_body import RequestBody

BucketName = Literal["already_imported", "new", "renewal", "updated", "to_review", "blocked"]
CampaignSource = Literal["setting", "environment", "default"]


class MembershipCampaignSetting(BaseModel):
    """campaign: as saved in Paramètres ("" when not set); resolved: the form slug the import reads."""
    campaign: str
    resolved: str
    source: CampaignSource


class MembershipCampaignUpdate(RequestBody):
    """Slug or HelloAsso URL of the membership form; empty: back to the default."""
    campaign: str = ""


class BucketCounts(BaseModel):
    already_imported: int
    new: int
    renewal: int
    updated: int
    to_review: int
    blocked: int


class MembershipRow(BaseModel):
    """One HelloAsso registration and what the import would do with it."""
    item_id: int
    bucket: BucketName
    reason: str
    order_ref: str
    order_date: str
    last_name: str
    first_name: str
    birth_date: str
    licence: str
    tarif_name: str
    amount: float
    status: str


class MembershipPreview(BaseModel):
    """blocked_reason: the whole campaign is refused (another season), every row is then blocked."""
    status: Literal["success"]
    season: str
    campaign: str
    blocked_reason: Optional[str]
    counts: BucketCounts
    rows: List[MembershipRow]
