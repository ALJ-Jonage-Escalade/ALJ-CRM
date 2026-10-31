"""Import of the HelloAsso membership campaign into the members (plans/helloasso-membership-import.md).

Thin orchestration, no business rule: the campaign comes from the app settings, HelloAsso gives the items, the domain
maps and classifies them. Knows nothing about HTTP: failures are raised as services.errors.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from domain.members.helloasso_membership import (
    MembershipCampaign,
    default_membership_campaign,
    map_membership_items,
    parse_membership_campaign,
)
from domain.members.membership_import import Decision, ImportPlan, StaleDecisions, apply_decisions, plan_membership_import
from infrastructure.firestore.app_settings import AppSettingsRepository
from infrastructure.helloasso import api as helloasso_api
from infrastructure.sqlite.membership_import import AppliedWrite, MembershipImportRepository
from services.errors import Conflict, InvalidRequest, UpstreamUnavailable
from services.members.seasons import SeasonService

CAMPAIGN_SETTING = "HELLOASSO_MEMBERSHIP_CAMPAIGN"
# Former setting of the desktop app (environment / .env), still read when the app setting is empty
CAMPAIGN_ENV = "CAMPAIGN_SLUG"

CampaignSource = Literal["setting", "environment", "default"]


@dataclass(frozen=True)
class ImportResult:
    plan: ImportPlan  # the plan recomputed on confirm, the decisions applied to it
    applied: list[AppliedWrite]


@dataclass(frozen=True)
class CampaignSetting:
    """The membership campaign setting as saved, and the campaign it resolves to."""
    reference: str  # as saved in Paramètres, "" when not set
    source: CampaignSource
    campaign: MembershipCampaign


def _parse(reference: str) -> MembershipCampaign:
    try:
        return parse_membership_campaign(reference)
    except ValueError as e:
        raise InvalidRequest(str(e), "invalid_campaign") from e


class MembershipImportService:

    @staticmethod
    def active_season() -> str:
        return SeasonService.list_seasons()["active"]

    @staticmethod
    def campaign_setting() -> CampaignSetting:
        """Resolution order: app setting, then the CAMPAIGN_SLUG environment variable, then the slug of the season."""
        reference = (AppSettingsRepository.get(CAMPAIGN_SETTING) or "").strip()
        if reference:
            return CampaignSetting(reference, "setting", _parse(reference))
        from_env = (os.environ.get(CAMPAIGN_ENV) or "").strip()
        if from_env:
            return CampaignSetting("", "environment", _parse(from_env))
        default = default_membership_campaign(MembershipImportService.active_season())
        return CampaignSetting("", "default", _parse(default))

    @staticmethod
    def save_campaign(reference: str) -> CampaignSetting:
        """Saves the campaign (slug or HelloAsso URL; empty: back to the default). Refuses a reference it cannot read."""
        reference = reference.strip()
        if reference:
            _parse(reference)
        AppSettingsRepository.save(CAMPAIGN_SETTING, reference)
        return MembershipImportService.campaign_setting()

    @staticmethod
    def preview() -> ImportPlan:
        """What the import would do now, for the active season. Writes nothing."""
        return MembershipImportService._plan(MembershipImportService.active_season())

    @staticmethod
    def import_(season: str, decisions: dict[int, Decision]) -> ImportResult:
        """Reads HelloAsso again, recomputes the plan and applies the admin's decisions (keyed by HelloAsso item id).
        Refused (Conflict) when the campaign is blocked or the decisions no longer match: nothing is then written.
        Sends no e-mail."""
        active = MembershipImportService.active_season()
        if season != active:
            raise Conflict(f"L'aperçu portait sur la saison {season}, la saison active est {active} : relancez l'aperçu.",
                           "stale_decisions")
        plan = MembershipImportService._plan(active)
        if plan.blocked_reason:
            raise Conflict(plan.blocked_reason, "campaign_blocked")
        try:
            writes = apply_decisions(plan, decisions)
        except StaleDecisions as e:
            raise Conflict(f"{e} Relancez l'aperçu.", "stale_decisions") from e
        return ImportResult(plan, MembershipImportRepository.apply(writes, active))

    @staticmethod
    def _plan(season: str) -> ImportPlan:
        campaign = MembershipImportService.campaign_setting().campaign
        try:
            items = helloasso_api.fetch_form_items(campaign.form_type, campaign.slug)
        except helloasso_api.HelloAssoApiError as e:
            raise UpstreamUnavailable(e.message, e.code) from e
        return plan_membership_import(map_membership_items(items), season=season, campaign_slug=campaign.slug)
