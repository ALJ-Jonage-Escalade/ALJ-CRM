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


class MembershipChange(BaseModel):
    """A value HelloAsso changed since the last import: in the CRM now (crm), as HelloAsso gave it last time (before),
    as HelloAsso gives it now (after). Amounts in euros, two decimals."""
    field: Literal["status", "tarif_name", "amount"]
    crm: str
    before: str
    after: str


class MembershipRow(BaseModel):
    """One HelloAsso registration and what the import would do with it. to_review rows: the candidate members, and
    whether a new member can be created from it (never without a birth date). Dates as HelloAsso gives them (ISO),
    "" when missing: order_date the registration, payment_date the first payment, refund_date the refund (status
    Refunded / Refunding)."""
    item_id: int
    bucket: BucketName
    reason: str
    order_ref: str
    order_date: str
    payment_date: str
    refund_date: str
    last_name: str
    first_name: str
    birth_date: str
    licence: str
    tarif_name: str
    amount: float
    status: str
    candidates: List[MembershipCandidate]
    can_create: bool
    changes: List[MembershipChange]


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
    """history_id: the import's entry in the history."""
    status: Literal["success"]
    season: str
    history_id: str
    counts: ImportCounts
    created: List[ImportedMember]
    renewed: List[ImportedMember]
    updated: List[ImportedMember]


class MembershipLastImport(BaseModel):
    """at: ISO date (UTC); author: e-mail of the admin who ran it."""
    at: str
    author: str
    season: str
    campaign: str


class MembershipLastSync(BaseModel):
    """The latest import, null before the first one."""
    last_sync: Optional[MembershipLastImport]
