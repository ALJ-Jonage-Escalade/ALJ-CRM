"""Which address an e-mail may leave from: the sending account or one of its verified aliases, never another one
(Gmail would rewrite it, an SMTP server would fail DMARC). Every send path resolves its sender here."""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

from domain.errors import Forbidden
from infrastructure import runtime_env
from infrastructure.mail import send_as
from infrastructure.mail.sender import MailError
from infrastructure.timed_cache import TimedCache

logger = logging.getLogger("alj")

CACHE_SECONDS = 300
_cache: TimedCache[str, "AllowedSenders"] = TimedCache(CACHE_SECONDS)


class AllowedSenders(TypedDict):
    account: str  # the sending account: the default sender
    aliases: list[str]  # every allowed address, the account first
    error: str  # why the list holds only the account (aliases unreadable); empty otherwise


def _load() -> tuple[AllowedSenders, float]:
    account = send_as.sending_account()
    try:
        aliases = send_as.read_aliases()
    except MailError as e:
        logger.warning("Alias d'envoi illisibles, seul le compte %s est autorisé : %s", account, e)
        # Not kept: the next call asks again
        return AllowedSenders(account=account, aliases=[account] if account else [], error=str(e)), 0
    addresses: list[str] = [account] if account else []
    for alias in aliases:
        if alias.lower() not in {address.lower() for address in addresses}:
            addresses.append(alias.lower())
    return AllowedSenders(account=account, aliases=addresses, error=""), CACHE_SECONDS


def allowed_senders() -> AllowedSenders:
    """The account and its aliases, kept 5 minutes (dev: read every time, an edited dev.env applies at once)."""
    if runtime_env.is_dev():
        return _load()[0]
    return _cache.get_or_load_expiring("senders", _load)


def forget_allowed_senders() -> None:
    """The next call reads the aliases again (tests)."""
    _cache.invalidate()


def _matching(senders: AllowedSenders, sender_email: str) -> Optional[str]:
    """The allowed address this sender is (case ignored); the account when empty; None when not allowed."""
    wanted = sender_email.strip().lower()
    if not wanted:
        return senders["account"]
    return next((address for address in senders["aliases"] if address.lower() == wanted), None)


def is_allowed_sender(sender_email: Optional[str], senders: Optional[AllowedSenders] = None) -> bool:
    """An empty sender (the account), the account or one of its aliases. `senders`: the list already read."""
    return _matching(senders or allowed_senders(), sender_email or "") is not None


def refusal(sender_email: str, senders: Optional[AllowedSenders] = None) -> str:
    """Why this sender may not be used, and what to do about it."""
    senders = senders or allowed_senders()
    hint = f" ({senders['error']})" if senders["error"] else ""
    return (f"Adresse d'expédition non autorisée : {sender_email.strip()}. Ajoutez-la comme alias « Envoyer des e-mails en "
            f"tant que » du compte {senders['account']}, ou choisissez une autre adresse{hint}.")


def resolve_sender(sender_email: Optional[str]) -> str:
    """The address to send from: the account when empty, else the allowed address it matches.
    Forbidden when it is neither the account nor one of its verified aliases."""
    senders = allowed_senders()
    address = _matching(senders, sender_email or "")
    if address is None:
        raise Forbidden(refusal(sender_email or "", senders), "sender_not_allowed")
    return address
