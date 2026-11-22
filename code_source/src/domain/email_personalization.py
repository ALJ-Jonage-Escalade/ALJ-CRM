"""Personalisation of an e-mail's subject and body: the values of the {…} variables (domain/email_variables.py),
taken from the recipient and, for a competition e-mail, from the competition."""

from __future__ import annotations

from typing import Any, Mapping, Optional, TypedDict

from domain.email_variables import render_template
from domain.utils import format_amount


class TemplateRecipient(TypedDict, total=False):
    """What the variables read from a recipient (a member row of the member pages, or a resolved recipient)."""
    first_name: str
    last_name: str
    licence_ffme: str
    tarif_name: str
    season_name: str
    amount: float | str | None  # the membership amount, formatted for the e-mail


def template_recipient(member: Mapping[str, Any]) -> TemplateRecipient:  # Any: a member row, values of any type
    """The recipient fields of a member row (MemberService)."""
    return TemplateRecipient(
        first_name=str(member.get("first_name") or ""),
        last_name=str(member.get("last_name") or ""),
        licence_ffme=str(member.get("licence_ffme") or ""),
        tarif_name=str(member.get("tarif_name") or ""),
        season_name=str(member.get("season_name") or ""),
        amount=member.get("amount"),
    )


def template_values(recipient: TemplateRecipient, competition_context: Optional[Mapping[str, Any]] = None,  # Any: shown as text
                    extra_values: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """The value of each variable for this recipient: the names written as on official documents (Prénom, NOM), the
    amount in the French format, then the competition's values and the extra ones (the problems of a correction request)."""
    context = competition_context or {}
    values = {
        "first_name": str(recipient.get("first_name") or "").strip().title(),
        "last_name": str(recipient.get("last_name") or "").strip().upper(),
        "num_licence": str(recipient.get("licence_ffme") or ""),
        "tarif": str(recipient.get("tarif_name") or ""),
        "season": str(recipient.get("season_name") or ""),
        "amount": format_amount(recipient.get("amount")),
    }
    for key in ("name_competition", "no_competition", "date_competition", "montant_competition", "whatsapp_link"):
        values[key] = str(context.get(key) or "")
    return {**values, **(extra_values or {})}


def apply_template_variables(text: Optional[str], recipient: TemplateRecipient,
                             competition_context: Optional[Mapping[str, Any]] = None,  # Any: context values, shown as text
                             escape_html: bool = False, extra_values: Optional[Mapping[str, str]] = None) -> str:
    """The subject or body with its variables filled for this recipient (see template_values); an empty value leaves
    nothing, and the line of an empty WhatsApp link goes away.

    escape_html=True: values are HTML-escaped, for a template already converted to HTML
    (member data comes from the public HelloAsso form and must never add markup).
    """
    return render_template(text, template_values(recipient, competition_context, extra_values), escape_html=escape_html)
