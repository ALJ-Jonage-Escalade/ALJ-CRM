"""Import of the HelloAsso membership campaign into the members (admin, api_auth.py): preview, import, last import."""

from __future__ import annotations

from typing import Optional, get_args

from fastapi import APIRouter, Request

from api.members.helloasso_import_schemas import (
    CorrectionEmail,
    CorrectionRequestBody,
    CorrectionRequestPreview,
    CorrectionRequestResult,
    BucketCounts,
    ImportCounts,
    ImportedMember,
    MembershipCandidate,
    MembershipChange,
    MembershipCorrection,
    MembershipCorrectionRequest,
    MembershipImportRequest,
    MembershipIssue,
    MembershipImportResult,
    MembershipLastImport,
    MembershipLastSync,
    MembershipMember,
    MembershipPreview,
    MembershipPreviewRequest,
    MembershipRequest,
    MembershipRow,
    MembershipValueCheck,
    MembershipValueCheckRequest,
)
from api.auth.me import author_of
from api.responses import error_responses
from domain.email_log import LastRequest
from domain.members.import_corrections import helloasso_value
from domain.members.member_data_rules import DataIssue, IssueField
from domain.members.membership_import import Decision, ImportPlan, KnownMember, PlanEntry, WriteAction, season_membership
from infrastructure.sqlite.membership_import import AppliedWrite
from services.communications.email_log import last_correction_requests_by_item
from services.members import correction_requests
from services.members.helloasso_import import ImportResult
from services.members.helloasso_import import MembershipImportService as Service

router = APIRouter()


def _candidate(member: KnownMember) -> MembershipCandidate:
    return MembershipCandidate(user_id=member.user_id, last_name=member.last_name, first_name=member.first_name,
                               birth_date=member.birth_date, licence=member.licence)


def _issue(issue: DataIssue) -> MembershipIssue:
    return MembershipIssue(field=issue.field, code=issue.code, message=issue.message, blocking=issue.blocking)


def _row(entry: PlanEntry, members: dict[int, KnownMember], requests: dict[int, LastRequest]) -> MembershipRow:
    record = entry.record
    request = requests.get(entry.item_id)
    matched = members.get(entry.member_id) if entry.member_id is not None else None
    return MembershipRow(
        item_id=record.item_id, bucket=entry.bucket, reason=entry.reason, order_ref=record.order_ref,
        order_date=record.order_date, payment_date=record.payment_date,
        refund_date=record.refund_date, last_name=record.last_name, first_name=record.first_name,
        birth_date=record.birth_date or record.birth_date_raw, licence=record.licence, tarif_name=record.tarif_name,
        amount=record.amount, status=record.status, can_create=entry.can_create,
        candidates=[_candidate(member) for member in entry.candidates],
        attached_to=_candidate(entry.attached_to) if entry.attached_to else None,
        matched_member=_candidate(matched) if matched else None,
        last_request=MembershipRequest(at=request["at"], author=request["author"]) if request else None,
        changes=[MembershipChange(field=change.field, crm=change.crm, before=change.before, after=change.after)
                 for change in entry.changes],
        issues=[_issue(issue) for issue in entry.issues],
        values={field: helloasso_value(record, field) for field in get_args(IssueField)},
        corrections=[MembershipCorrection(field=correction.field, value=correction.value, helloasso_value=correction.helloasso_value,
                                          author=correction.author, at=correction.at) for correction in entry.corrections],
    )


def _preview(plan: ImportPlan) -> MembershipPreview:
    members = {member.user_id: member for member in plan.members}
    requests = last_correction_requests_by_item()
    return MembershipPreview(
        status="success", season=plan.season, campaign=plan.campaign_slug, blocked_reason=plan.blocked_reason,
        counts=BucketCounts(**plan.counts()), rows=[_row(entry, members, requests) for entry in plan.entries],
        members=[MembershipMember(**_candidate(member).model_dump(), membership=season_membership(plan, member.user_id).kind)
                 for member in sorted(plan.members, key=lambda m: (m.last_name.casefold(), m.first_name.casefold()))],
    )


@router.post("/api/helloasso/memberships/preview", response_model=MembershipPreview, responses=error_responses(400, 502))
def preview_membership_import(data: Optional[MembershipPreviewRequest] = None) -> MembershipPreview:
    """Reads the membership campaign on HelloAsso and sorts its registrations for the active season. Writes nothing."""
    return _preview(Service.preview(data.campaign if data else None))


@router.put("/api/helloasso/memberships/corrections/{item_id}/{field}", response_model=MembershipPreview,
            responses=error_responses(400, 404, 502))
def save_membership_correction(request: Request, item_id: int, field: IssueField, data: MembershipCorrectionRequest) -> MembershipPreview:
    """Saves the admin's correction of one field of a registration; answers the preview recomputed with it."""
    return _preview(Service.save_correction(item_id, field, data.value, author_of(request), data.campaign))


@router.delete("/api/helloasso/memberships/corrections/{item_id}/{field}", response_model=MembershipPreview,
               responses=error_responses(400, 502))
def remove_membership_correction(item_id: int, field: IssueField, campaign: Optional[str] = None) -> MembershipPreview:
    """Removes the correction of one field (HelloAsso's value applies again); answers the preview recomputed."""
    return _preview(Service.remove_correction(item_id, field, campaign))


@router.post("/api/helloasso/memberships/corrections/check", response_model=MembershipValueCheck)
def check_membership_value(data: MembershipValueCheckRequest) -> MembershipValueCheck:
    """Checks a value with the import's rules as the admin types it. Saves nothing."""
    value, issues = Service.check_value(data.field, data.value)
    return MembershipValueCheck(status="success", value=value, issues=[_issue(issue) for issue in issues])


@router.post("/api/helloasso/memberships/correction-requests/preview", response_model=CorrectionRequestPreview,
             responses=error_responses(400, 502))
def preview_correction_requests(data: CorrectionRequestBody) -> CorrectionRequestPreview:
    """The correction request of the first order of these registrations, as it would be sent. Sends nothing."""
    return CorrectionRequestPreview(status="success", example=CorrectionEmail(**correction_requests.example(data.item_ids, data.campaign)))


@router.post("/api/helloasso/memberships/correction-requests", response_model=CorrectionRequestResult,
             responses=error_responses(400, 502))
def send_correction_requests(request: Request, data: CorrectionRequestBody) -> CorrectionRequestResult:
    """Asks the families to fix their data: one e-mail per order, to the payer, recorded in the e-mail log."""
    return CorrectionRequestResult(status="success", **correction_requests.send(data.item_ids, author_of(request), data.campaign))


def _imported(applied: AppliedWrite, plan: ImportPlan) -> ImportedMember:
    record = next(entry.record for entry in plan.entries if entry.item_id == applied.item_id)
    last_name, first_name = record.last_name, record.first_name
    if applied.action == WriteAction.ASSIGN:  # the member chosen: the HelloAsso name is someone else's
        member = next(member for member in plan.members if member.user_id == applied.user_id)
        last_name, first_name = member.last_name, member.first_name
    return ImportedMember(item_id=applied.item_id, user_id=applied.user_id, purchase_id=applied.purchase_id,
                          last_name=last_name, first_name=first_name, tarif_name=record.tarif_name)


def _result(result: ImportResult) -> MembershipImportResult:
    def members(action: WriteAction) -> list[ImportedMember]:
        return [_imported(applied, result.plan) for applied in result.applied if applied.action == action]

    created, renewed, updated = members(WriteAction.CREATE), members(WriteAction.ATTACH), members(WriteAction.UPDATE)
    attached = members(WriteAction.ASSIGN)
    written = len(created) + len(renewed) + len(updated) + len(attached)
    return MembershipImportResult(
        status="success", season=result.plan.season, history_id=result.history_id,
        counts=ImportCounts(created=len(created), renewed=len(renewed), updated=len(updated), attached=len(attached),
                            skipped=len(result.plan.entries) - written),
        created=created, renewed=renewed, updated=updated, attached=attached,
    )


@router.post("/api/helloasso/memberships/import", response_model=MembershipImportResult, responses=error_responses(400, 409, 502))
def import_memberships(request: Request, data: MembershipImportRequest) -> MembershipImportResult:
    """Reads HelloAsso again and applies the admin's decisions to the recomputed plan, recorded in the history.
    Sends no e-mail."""
    decisions = {item_id: Decision(decision.bucket, decision.choice, decision.comment)
                 for item_id, decision in data.decisions.items()}
    return _result(Service.import_(data.season, decisions, author_of(request), data.campaign))


@router.get("/api/helloasso/memberships/last-sync", response_model=MembershipLastSync)
def last_membership_sync() -> MembershipLastSync:
    """When the latest import ran, and who ran it."""
    last = Service.last_import()
    if last is None:
        return MembershipLastSync(last_sync=None)
    return MembershipLastSync(last_sync=MembershipLastImport(at=last["at"], author=last["author"], season=last["season"],
                                                             campaign=last["campaign"]))
