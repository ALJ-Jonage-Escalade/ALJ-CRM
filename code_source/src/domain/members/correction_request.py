"""Correction requests to the families: what the club asks them to fix in their HelloAsso registration
(plans/helloasso-import-data-checks.md). Pure, no I/O.

One request per HelloAsso order, to the payer (an address HelloAsso already proved works), the primary club e-mail of
the registrations in copy when it is valid and another address. It lists, for each registration of the order, the
problems still present (a value the admin corrected is no longer one), with the values as typed. The family answers
by e-mail; the admin then types the correction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from domain.members.helloasso_membership import EMAIL_FIELD
from domain.members.membership_import import PlanEntry

# The template of the e-mail, shipped with the app (editable in Communications › Modèles)
CORRECTION_REQUEST_TEMPLATE = "Adhésion : informations à corriger"
# Its variable: the problems of each registration of the order
PROBLEMS_VARIABLE = "problemes"  # its key in domain/email_variables.py


@dataclass(frozen=True)
class CorrectionRequest:
    order_ref: str
    payer_first_name: str
    payer_last_name: str
    payer_email: str
    cc: tuple[str, ...]  # the primary club e-mails of the registrations, valid and not the payer's
    item_ids: tuple[int, ...]  # the registrations with problems, in the order of the plan
    problems: str  # the text of PROBLEMS_VARIABLE


def _problems(entry: PlanEntry) -> str:
    record = entry.record
    lines = [f"{record.first_name.strip()} {record.last_name.strip().upper()} :", *(f"- {issue.message}" for issue in entry.issues)]
    return "\n".join(lines)


def _copy(entry: PlanEntry) -> str:
    """The registration's primary club e-mail, "" when it has a problem."""
    if any(issue.field == "email" for issue in entry.issues):
        return ""
    return entry.record.custom_fields.get(EMAIL_FIELD, "").strip()


def correction_requests(entries: Iterable[PlanEntry]) -> list[CorrectionRequest]:
    """The requests of these registrations, one per order, in the order of the plan; the registrations without
    problem are left out."""
    orders: dict[str, list[PlanEntry]] = {}
    for entry in entries:
        if entry.issues:
            orders.setdefault(entry.record.order_ref, []).append(entry)
    requests = []
    for order_ref, order in orders.items():
        payer = order[0].record
        copies = dict.fromkeys(address for address in map(_copy, order)
                               if address and address.casefold() != payer.payer_email.strip().casefold())
        requests.append(CorrectionRequest(
            order_ref=order_ref, payer_first_name=payer.payer_first_name, payer_last_name=payer.payer_last_name,
            payer_email=payer.payer_email, cc=tuple(copies), item_ids=tuple(entry.item_id for entry in order),
            problems="\n\n".join(_problems(entry) for entry in order),
        ))
    return requests
