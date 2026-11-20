"""Bodies of the HelloAsso membership import routes (api/members/helloasso_import.py), API contract of the Vue app."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from api.request_body import RequestBody
from domain.members.member_data_rules import IssueField
from domain.members.membership_import import Bucket, ChangedField, MembershipKind



class BucketCounts(BaseModel):
    already_imported: int
    new: int
    renewal: int
    updated: int
    to_review: int
    blocked: int


class MembershipCandidate(BaseModel):
    """A member a registration to review may be (choice "link:<user_id>"), or an imported one is attached to."""
    user_id: int
    last_name: str
    first_name: str
    birth_date: str
    licence: str


class MembershipChange(BaseModel):
    """A value HelloAsso changed since the last import: in the CRM now (crm), as HelloAsso gave it last time (before),
    as HelloAsso gives it now (after). Amounts in euros, two decimals."""
    field: ChangedField
    crm: str
    before: str
    after: str


class MembershipIssue(BaseModel):
    """A problem of a value the import would store: `blocking` (birth date only) holds the row in « À vérifier »."""
    field: IssueField
    code: str
    message: str
    blocking: bool


class MembershipRow(BaseModel):
    """One HelloAsso registration and what the import would do with it. to_review rows: the candidate members, and
    whether a new member can be created from it (never without a birth date). Dates as HelloAsso gives them (ISO),
    "" when missing: order_date the registration, payment_date the first payment, refund_date the refund (status
    Refunded / Refunding)."""
    item_id: int
    bucket: Bucket
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
    attached_to: Optional[MembershipCandidate] = None  # imported rows: the member, when their name is not the HelloAsso one
    issues: List[MembershipIssue]


class MembershipMember(BaseModel):
    """A member of the base a registration can be attached to by hand (choice "attach:<user_id>"). membership: theirs
    this season — none, manual (taken over by the attach), several_manual or helloasso (the attach is refused)."""
    user_id: int
    last_name: str
    first_name: str
    birth_date: str
    licence: str
    membership: MembershipKind


class MembershipPreview(BaseModel):
    """blocked_reason: the whole campaign is refused (another season), every row is then blocked. members: every member
    of the base (any season), for the attach by hand."""
    status: Literal["success"]
    season: str
    campaign: str
    blocked_reason: Optional[str]
    counts: BucketCounts
    rows: List[MembershipRow]
    members: List[MembershipMember]


class MembershipDecision(RequestBody):
    """The admin's choice on a preview row: import / skip (new, renewal, updated rows), create / skip / link:<member id>
    (rows to review), attach:<member id> (new, renewal and to-review rows: given by hand to any member, `comment`
    required). bucket: the bucket the preview showed the row in (a row that changed since is refused)."""
    bucket: Bucket
    choice: str
    comment: str = Field(default="", max_length=1000)


class MembershipPreviewRequest(RequestBody):
    """campaign: slug of the membership form to read for this sync only (never saved); null or blank: the active one
    (Paramètres › Campagnes)."""
    campaign: Optional[str] = None


class MembershipImportRequest(RequestBody):
    """decisions: by HelloAsso item id; a row without decision is skipped. campaign: the one of the preview."""
    season: str
    campaign: Optional[str] = None
    decisions: Dict[int, MembershipDecision]


class ImportedMember(BaseModel):
    """A member the import wrote, for the link to their record (attached: the member chosen, not the HelloAsso name)."""
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
    attached: int  # given by hand to a member
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
    attached: List[ImportedMember]


class MembershipLastImport(BaseModel):
    """at: ISO date (UTC); author: e-mail of the admin who ran it."""
    at: str
    author: str
    season: str
    campaign: str


class MembershipLastSync(BaseModel):
    """The latest import, null before the first one."""
    last_sync: Optional[MembershipLastImport]
