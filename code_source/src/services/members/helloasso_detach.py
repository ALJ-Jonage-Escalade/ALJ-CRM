"""Detaching a membership from HelloAsso (#84): undoes a wrong match of the membership import from the member record.

The purchase is deleted (with its options, and its order left empty), the member is left as is; the next import sees
the HelloAsso registration as unknown again, so the admin can attach it to the right member. Knows nothing about HTTP:
failures are raised as domain.errors.
"""

from __future__ import annotations

import datetime

from domain.errors import InvalidRequest, NotFound
from infrastructure.firestore.membership_import_history import DetachHistoryEntry, MembershipImportHistory
from infrastructure.sqlite.membership_import import HelloAssoMembership, MembershipImportRepository


def detach_from_helloasso(purchase_id: int, reason: str, author: str) -> HelloAssoMembership:
    """Deletes the membership `purchase_id` linked to a HelloAsso registration; returns what was deleted. `author`:
    e-mail of the admin."""
    if not reason.strip():
        raise InvalidRequest("Indiquez la raison du détachement : elle est gardée dans l'historique des imports.")
    membership = MembershipImportRepository.membership(purchase_id)
    if membership is None:
        raise NotFound("Adhésion introuvable : la liste a peut-être changé, rechargez la page.")
    if membership.item_id is None:
        raise InvalidRequest(f"L'adhésion {membership.season} de {membership.member} ne vient pas d'une inscription HelloAsso.")
    MembershipImportRepository.delete_membership(purchase_id)
    MembershipImportHistory.record(DetachHistoryEntry(
        kind="detach", at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), author=author,
        season=membership.season, item_id=membership.item_id, order_ref=membership.order_ref, user_id=membership.user_id,
        member=membership.member, purchase_id=membership.purchase_id, tarif=membership.tarif, amount=membership.amount,
        reason=reason.strip()))
    return membership
