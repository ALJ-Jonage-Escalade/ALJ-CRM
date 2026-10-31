"""Import of the HelloAsso membership campaign into the members (admin, api_auth.py): campaign setting, preview."""

from __future__ import annotations

from fastapi import APIRouter

from api.members.helloasso_import_schemas import (
    BucketCounts,
    MembershipCampaignSetting,
    MembershipCampaignUpdate,
    MembershipPreview,
    MembershipRow,
)
from api.responses import error_responses
from domain.members.membership_import import ImportPlan, PlanEntry
from services.members.helloasso_import import CampaignSetting
from services.members.helloasso_import import MembershipImportService as Service

router = APIRouter()


def _setting(setting: CampaignSetting) -> MembershipCampaignSetting:
    return MembershipCampaignSetting(campaign=setting.reference, resolved=setting.campaign.slug, source=setting.source)


def _row(entry: PlanEntry) -> MembershipRow:
    record = entry.record
    return MembershipRow(
        item_id=record.item_id, bucket=entry.bucket.value, reason=entry.reason, order_ref=record.order_ref,
        order_date=record.order_date, last_name=record.last_name, first_name=record.first_name,
        birth_date=record.birth_date or record.birth_date_raw, licence=record.licence, tarif_name=record.tarif_name,
        amount=record.amount, status=record.status,
    )


def _preview(plan: ImportPlan) -> MembershipPreview:
    return MembershipPreview(
        status="success", season=plan.season, campaign=plan.campaign_slug, blocked_reason=plan.blocked_reason,
        counts=BucketCounts(**plan.counts()), rows=[_row(entry) for entry in plan.entries],
    )


@router.get("/api/settings/helloasso-membership", response_model=MembershipCampaignSetting, responses=error_responses(400))
def get_membership_campaign() -> MembershipCampaignSetting:
    return _setting(Service.campaign_setting())


@router.post("/api/settings/helloasso-membership", response_model=MembershipCampaignSetting, responses=error_responses(400))
def save_membership_campaign(data: MembershipCampaignUpdate) -> MembershipCampaignSetting:
    return _setting(Service.save_campaign(data.campaign))


@router.post("/api/helloasso/memberships/preview", response_model=MembershipPreview, responses=error_responses(400, 502))
def preview_membership_import() -> MembershipPreview:
    """Reads the membership campaign on HelloAsso and sorts its registrations for the active season. Writes nothing."""
    return _preview(Service.preview())
