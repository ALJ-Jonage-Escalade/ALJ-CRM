"""Personalisation of an e-mail's subject and body: the {…} variables of the club's templates, filled from the
recipient and, for a competition e-mail, from the competition."""

from __future__ import annotations

import html
import re
from typing import Any, Mapping, Optional, TypedDict


class TemplateRecipient(TypedDict, total=False):
    """What the variables read from a recipient (a member row of the member pages, or a resolved recipient)."""
    first_name: str
    last_name: str
    licence_ffme: str
    tarif_name: str
    season_name: str


def template_recipient(member: Mapping[str, Any]) -> TemplateRecipient:  # Any: a member row, values of any type
    """The recipient fields of a member row (MemberService)."""
    return TemplateRecipient(
        first_name=str(member.get("first_name") or ""),
        last_name=str(member.get("last_name") or ""),
        licence_ffme=str(member.get("licence_ffme") or ""),
        tarif_name=str(member.get("tarif_name") or ""),
        season_name=str(member.get("season_name") or ""),
    )


# Competition variables, replaced as written and capitalised ({lieu} and {Lieu})
_COMPETITION_KEYS = (
    "no_competition", "name_competition", "competition_nom", "montant_competition", "date_competition",
    "competition_date", "competition_deadline", "deadline", "lieu", "competition_lieu",
)
# Spellings of the WhatsApp variables found in the club's templates (including the historical "whatapp")
_WHATSAPP_BLOCK_KEYS = ("bloc_whatsapp", "bloc_whatapp", "whatsapp_bloc")
_WHATSAPP_LINK_KEYS = ("whatapp_Id", "whatsapp_id", "whatapp_id", "whatsapp_Id", "whatsapp_link", "whatapp_link")


def apply_template_variables(text: Optional[str], recipient: TemplateRecipient,
                             competition_context: Optional[Mapping[str, Any]] = None,  # Any: context values, shown as text
                             escape_html: bool = False) -> str:
    """Replaces the {…} variables of an e-mail subject or body:
    - {Prénom}/{Nom}/{first_name}/{last_name}/{prenom}/{nom}: the recipient's names; {num_licence}: their FFME licence;
      {tarif} and {season}: their group and season, when known;
    - competition variables ({no_competition}, {name_competition}, {montant_competition}, {date_competition}…,
      {whatapp_Id}, {bloc_whatsapp}), left as they are when missing from the context.

    escape_html=True: values are HTML-escaped, for a template already converted to HTML
    (member data comes from the public HelloAsso form and must never add markup).
    """
    if text is None:
        return ""
    context = competition_context or {}
    out = str(text)
    first = str(recipient.get("first_name") or "").strip().title()
    last = str(recipient.get("last_name") or "").strip().upper()
    licence = str(recipient.get("licence_ffme") or "").strip()
    tarif = str(recipient.get("tarif_name") or "").strip()
    season = str(recipient.get("season_name") or "").strip()

    def encode(value: str) -> str:
        return html.escape(value) if escape_html else value

    for key in ("{Prénom}", "{first_name}", "{prenom}"):
        out = out.replace(key, encode(first))
    for key in ("{Nom}", "{last_name}", "{nom}"):
        out = out.replace(key, encode(last))
    out = out.replace("{num_licence}", encode(licence))
    if tarif:
        out = out.replace("{tarif}", encode(tarif))
    if season:
        out = out.replace("{season}", encode(season))

    for key in _COMPETITION_KEYS:
        value = str(context.get(key) or "").strip()
        if value:
            out = out.replace("{" + key + "}", encode(value))
            out = out.replace("{" + key.title() + "}", encode(value))

    whatsapp_link = str(
        context.get("whatapp_Id")
        or context.get("whatsapp_link")
        or context.get("whatsapp_id")
        or context.get("whatapp_id")
        or context.get("whatsappLink")
        or ""
    ).strip()
    if whatsapp_link:
        block = encode(f"Voici le lien du groupe WhatApp dédié à cette compétition : {whatsapp_link}")
        for key in _WHATSAPP_BLOCK_KEYS:
            out = out.replace("{" + key + "}", block)
        for key in _WHATSAPP_LINK_KEYS:
            out = out.replace("{" + key + "}", encode(whatsapp_link))
    elif competition_context is not None:
        for key in _WHATSAPP_BLOCK_KEYS:
            out = out.replace("{" + key + "}", "")
        # No WhatsApp link configured: the line that shows it goes away
        out = re.sub(r"(?m)^[^\n]*\{(?:" + "|".join(_WHATSAPP_LINK_KEYS) + r")\}[^\n]*\r?\n?", "", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
    return out
