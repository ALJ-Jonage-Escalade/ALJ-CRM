"""Import of the HelloAsso membership campaign into the members (plans/helloasso-membership-import.md).

Thin orchestration, no business rule: the campaign is the one chosen in Paramètres › Campagnes (else CAMPAIGN_SLUG, else the
season's default form), HelloAsso gives the items, the domain maps and classifies them. Knows nothing about HTTP: failures are raised as domain.errors.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from domain.members.helloasso_membership import (
    MembershipCampaign,
    default_membership_campaign,
    map_membership_items,
    parse_membership_campaign,
)
from domain.members.membership_import import Decision, ImportPlan, StaleDecisions, apply_decisions, plan_membership_import
from infrastructure import runtime_env
from infrastructure.firestore.app_settings import HELLOASSO_MEMBERSHIP_CAMPAIGN, AppSettingsRepository
from infrastructure.firestore.client import FirestoreError
from infrastructure.firestore.membership_import_history import ImportedItem, ImportHistoryEntry, MembershipImportHistory
from infrastructure.helloasso import api as helloasso_api
from infrastructure.mail.mail_domains import MailDomainCheck
from infrastructure.security.secret_store import SecretStore
from infrastructure.sqlite.membership_import import AppliedWrite, MembershipImportRepository, MembershipWriteRefused
from domain.errors import Conflict, InvalidRequest, UpstreamUnavailable
from services.members.seasons import SeasonService

logger = logging.getLogger("alj")

# Server variable naming the membership form while none is chosen in Paramètres (temporary fallback)
CAMPAIGN_ENV = "CAMPAIGN_SLUG"


@dataclass(frozen=True)
class ImportResult:
    plan: ImportPlan  # the plan recomputed on confirm, the decisions applied to it
    applied: list[AppliedWrite]
    history_id: str


def _parse(reference: str) -> MembershipCampaign:
    try:
        return parse_membership_campaign(reference)
    except ValueError as e:
        raise InvalidRequest(str(e), "invalid_campaign") from e


def _imported_item(item_id: int, bucket: str, action: str, decision: Optional[Decision]) -> ImportedItem:
    item = ImportedItem(item_id=item_id, bucket=bucket, action=action, decision=decision.choice if decision else "skip")
    if decision and decision.comment.strip():
        item["comment"] = decision.comment.strip()
    return item


class MembershipImportService:

    @staticmethod
    def active_season() -> str:
        return SeasonService.list_seasons()["active"]

    @staticmethod
    def campaign_reference() -> str:
        """Reference of the membership form, read on each call (a change applies without restart): the campaign chosen
        in Paramètres › Campagnes, else the CAMPAIGN_SLUG server variable, else the club's default form of the season.
        Firestore unreadable: the variable, then the default."""
        try:
            chosen = (AppSettingsRepository.get(HELLOASSO_MEMBERSHIP_CAMPAIGN) or "").strip()
        except FirestoreError as e:
            logger.warning("Membership campaign setting unreadable, falling back to %s: %s", CAMPAIGN_ENV, e)
            chosen = ""
        return (chosen or (SecretStore.get_secret(CAMPAIGN_ENV) or "").strip()
                or default_membership_campaign(MembershipImportService.active_season()))

    @staticmethod
    def campaign_slug() -> str:
        """Slug of campaign_reference, shown by Paramètres › Campagnes. A reference that cannot be read gives its last
        URL segment."""
        reference = MembershipImportService.campaign_reference()
        try:
            return parse_membership_campaign(reference).slug
        except ValueError:
            return [segment for segment in reference.split("/") if segment.strip()][-1]

    @staticmethod
    def campaign(chosen: Optional[str] = None) -> MembershipCampaign:
        """The membership form read by the import: `chosen` (a campaign picked for this sync only, never saved), else
        campaign_reference. InvalidRequest when it cannot be read."""
        return _parse((chosen or "").strip() or MembershipImportService.campaign_reference())

    @staticmethod
    def preview(chosen_campaign: Optional[str] = None) -> ImportPlan:
        """What the import would do now, for the active season. Writes nothing. `chosen_campaign`: see campaign()."""
        return MembershipImportService._plan(MembershipImportService.active_season(), chosen_campaign)

    @staticmethod
    def import_(season: str, decisions: dict[int, Decision], author: str, chosen_campaign: Optional[str] = None) -> ImportResult:
        """Reads HelloAsso again, recomputes the plan and applies the admin's decisions (keyed by HelloAsso item id),
        then records the import in the history. Refused (Conflict) when the campaign is blocked or the decisions no
        longer match: nothing is then written. Sends no e-mail. `author`: e-mail of the admin; `chosen_campaign`: the
        one of the preview (see campaign())."""
        active = MembershipImportService.active_season()
        if season != active:
            raise Conflict(f"L'aperçu portait sur la saison {season}, la saison active est {active} : relancez l'aperçu.",
                           "stale_decisions")
        plan = MembershipImportService._plan(active, chosen_campaign)
        if plan.blocked_reason:
            raise Conflict(plan.blocked_reason, "campaign_blocked")
        try:
            writes = apply_decisions(plan, decisions)
        except StaleDecisions as e:
            raise Conflict(f"{e} Relancez l'aperçu.", "stale_decisions") from e
        try:
            applied = MembershipImportRepository.apply(writes, active, author=author)
        except MembershipWriteRefused as e:
            raise Conflict(f"{e} Rien n'a été importé.", "write_refused") from e
        actions = {written.item_id: written.action.value for written in applied}
        items = [_imported_item(entry.item_id, entry.bucket.value, actions.get(entry.item_id, ""), decisions.get(entry.item_id))
                 for entry in plan.entries]
        history_id = MembershipImportHistory.record(ImportHistoryEntry(
            at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), author=author, season=plan.season,
            campaign=plan.campaign_slug, counts=plan.counts(), items=items))
        return ImportResult(plan, applied, history_id)

    @staticmethod
    def last_import() -> Optional[ImportHistoryEntry]:
        return MembershipImportHistory.latest()

    @staticmethod
    def _plan(season: str, chosen_campaign: Optional[str]) -> ImportPlan:
        campaign = MembershipImportService.campaign(chosen_campaign)
        try:
            items = helloasso_api.fetch_form_items(campaign.form_type, campaign.slug)
        except helloasso_api.HelloAssoApiError as e:
            raise UpstreamUnavailable(e.message, e.code) from e
        # The e-mail domains are looked up on Cloud Run only: dev and tests never reach the network
        domain_check = MailDomainCheck() if runtime_env.is_cloud_run() else None
        return plan_membership_import(map_membership_items(items), season=season, campaign_slug=campaign.slug,
                                      snapshot=MembershipImportRepository.snapshot(), domain_accepts_mail=domain_check)
