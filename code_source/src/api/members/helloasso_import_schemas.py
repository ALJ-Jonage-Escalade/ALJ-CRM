"""Bodies of the HelloAsso membership import routes (api/members/helloasso_import.py), API contract of the Vue app."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

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


class MembershipCandidate(BaseModel):
    """A member a registration to review may be (choice "link:<user_id>")."""
    user_id: int
    last_name: str
    first_name: str
    birth_date: str
    licence: str


class MembershipRow(BaseModel):
    """One HelloAsso registration and what the import would do with it. to_review rows: the candidate members, and
    whether a new member can be created from it (never without a birth date)."""
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
    candidates: List[MembershipCandidate]
    can_create: bool


class MembershipPreview(BaseModel):
    """blocked_reason: the whole campaign is refused (another season), every row is then blocked."""
    status: Literal["success"]
    season: str
    campaign: str
    blocked_reason: Optional[str]
    counts: BucketCounts
    rows: List[MembershipRow]


class MembershipDecision(RequestBody):
    """The admin's choice on a preview row: import / skip (new, renewal, updated rows), create / skip / link:<member id>
    (rows to review). bucket: the bucket the preview showed the row in (a row that changed since is refused)."""
    bucket: BucketName
    choice: str


class MembershipImportRequest(RequestBody):
    """decisions: by HelloAsso item id; a row without decision is skipped."""
    season: str
    decisions: Dict[int, MembershipDecision]


class ImportedMember(BaseModel):
    """A member the import wrote, for the link to their record."""
    item_id: int
    user_id: int
    purchase_id: int
    last_name: str
    first_name: str
    tarif_name: str


class ImportCounts(BaseModel):
    created: int
    renewed: int
    updated: int
    skipped: int  # rows of the plan nothing was written for


class MembershipImportResult(BaseModel):
    status: Literal["success"]
    season: str
    counts: ImportCounts
    created: List[ImportedMember]
    renewed: List[ImportedMember]
    updated: List[ImportedMember]
