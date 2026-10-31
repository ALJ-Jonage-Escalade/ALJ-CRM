"""Import of the HelloAsso membership campaign into the members (admin, api_auth.py): preview, import, last import."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.members.helloasso_import_schemas import (
    BucketCounts,
    ImportCounts,
    ImportedMember,
    MembershipCandidate,
    MembershipChange,
    MembershipImportRequest,
    MembershipImportResult,
    MembershipLastImport,
    MembershipLastSync,
    MembershipPreview,
    MembershipRow,
)
from api.admin.access import author_of
from api.responses import error_responses
from domain.members.helloasso_membership import MembershipRecord
from domain.members.membership_import import Bucket, Decision, ImportPlan, PlanEntry, WriteAction
from infrastructure.sqlite.membership_import import AppliedWrite
from services.members.helloasso_import import ImportResult
from services.members.helloasso_import import MembershipImportService as Service

router = APIRouter()


def _row(entry: PlanEntry) -> MembershipRow:
    record = entry.record
    return MembershipRow(
        item_id=record.item_id, bucket=entry.bucket.value, reason=entry.reason, order_ref=record.order_ref,
        order_date=record.order_date, payment_date=record.payment_date,
        refund_date=record.refund_date, last_name=record.last_name, first_name=record.first_name,
        birth_date=record.birth_date or record.birth_date_raw, licence=record.licence, tarif_name=record.tarif_name,
        amount=record.amount, status=record.status, can_create=entry.can_create,
        candidates=[MembershipCandidate(user_id=member.user_id, last_name=member.last_name, first_name=member.first_name,
                                        birth_date=member.birth_date, licence=member.licence) for member in entry.candidates],
        changes=[MembershipChange(field=change.field, crm=change.crm, before=change.before, after=change.after)
                 for change in entry.changes],
    )


def _preview(plan: ImportPlan) -> MembershipPreview:
    return MembershipPreview(
        status="success", season=plan.season, campaign=plan.campaign_slug, blocked_reason=plan.blocked_reason,
        counts=BucketCounts(**plan.counts()), rows=[_row(entry) for entry in plan.entries],
    )


@router.post("/api/helloasso/memberships/preview", response_model=MembershipPreview, responses=error_responses(400, 502))
def preview_membership_import() -> MembershipPreview:
    """Reads the membership campaign on HelloAsso and sorts its registrations for the active season. Writes nothing."""
    return _preview(Service.preview())


def _imported(applied: AppliedWrite, records: dict[int, MembershipRecord]) -> ImportedMember:
    record = records[applied.item_id]
    return ImportedMember(item_id=applied.item_id, user_id=applied.user_id, purchase_id=applied.purchase_id,
                          last_name=record.last_name, first_name=record.first_name, tarif_name=record.tarif_name)


def _result(result: ImportResult) -> MembershipImportResult:
    records = {entry.item_id: entry.record for entry in result.plan.entries}

    def members(action: WriteAction) -> list[ImportedMember]:
        return [_imported(applied, records) for applied in result.applied if applied.action == action]

    created, renewed, updated = members(WriteAction.CREATE), members(WriteAction.ATTACH), members(WriteAction.UPDATE)
    written = len(created) + len(renewed) + len(updated)
    return MembershipImportResult(
        status="success", season=result.plan.season, history_id=result.history_id,
        counts=ImportCounts(created=len(created), renewed=len(renewed), updated=len(updated), skipped=len(result.plan.entries) - written),
        created=created, renewed=renewed, updated=updated,
    )


@router.post("/api/helloasso/memberships/import", response_model=MembershipImportResult, responses=error_responses(400, 409, 502))
def import_memberships(request: Request, data: MembershipImportRequest) -> MembershipImportResult:
    """Reads HelloAsso again and applies the admin's decisions to the recomputed plan, recorded in the history.
    Sends no e-mail."""
    decisions = {item_id: Decision(Bucket(decision.bucket), decision.choice) for item_id, decision in data.decisions.items()}
    return _result(Service.import_(data.season, decisions, author_of(request)))


@router.get("/api/helloasso/memberships/last-sync", response_model=MembershipLastSync)
def last_membership_sync() -> MembershipLastSync:
    """When the latest import ran, and who ran it."""
    last = Service.last_import()
    if last is None:
        return MembershipLastSync(last_sync=None)
    return MembershipLastSync(last_sync=MembershipLastImport(at=last["at"], author=last["author"], season=last["season"],
                                                             campaign=last["campaign"]))
