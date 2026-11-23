"""The addresses the club's mail account can send as: its own address and the aliases the transport knows.

Gmail OAuth mode: the account (GMAIL_USER_EMAIL) and its "Send mail as" aliases, read from the Gmail API (only the
verified ones). SMTP mode (dev included): SMTP_FROM_EMAIL (else SMTP_USER) and the comma-separated variable
SMTP_SENDER_ALIASES. No rule here: services.communications.senders decides what may be sent as."""

from __future__ import annotations

import requests

from infrastructure.google.drive import GoogleDriveClient
from infrastructure.mail.sender import MailError, uses_gmail
from infrastructure.security.secret_store import SecretStore

SEND_AS_TIMEOUT_SECONDS = 10


def sending_account() -> str:
    """The address of the account that sends (empty: no configuration)."""
    if uses_gmail():
        return (SecretStore.get_secret("GMAIL_USER_EMAIL") or "").strip()
    return (SecretStore.get_secret("SMTP_FROM_EMAIL") or SecretStore.get_secret("SMTP_USER") or "").strip()


def read_aliases() -> list[str]:
    """The other addresses the account may send as, as the transport lists them. MailError when they cannot be read."""
    if uses_gmail():
        return _gmail_aliases()
    configured = SecretStore.get_secret("SMTP_SENDER_ALIASES") or ""
    return [address.strip() for address in configured.split(",") if address.strip()]


def _gmail_aliases() -> list[str]:
    """Gmail "Send mail as" entries that are the account or verified (a pending alias would be rewritten)."""
    try:
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/settings/sendAs",
            headers={"Authorization": f"Bearer {GoogleDriveClient.get_access_token()}"},
            timeout=SEND_AS_TIMEOUT_SECONDS,
        )
    except (requests.RequestException, ValueError) as e:  # ValueError: Google credentials missing
        raise MailError(f"Liste des alias Gmail inaccessible : {e}") from e
    if response.status_code == 403:
        raise MailError("Gmail refuse de lister les alias d'envoi : reconnectez le compte Google dans Paramètres.")
    if response.status_code != 200:
        raise MailError(f"Liste des alias Gmail inaccessible (HTTP {response.status_code}).")
    entries = response.json().get("sendAs") or []
    return [str(entry.get("sendAsEmail") or "").strip() for entry in entries
            if entry.get("isPrimary") or entry.get("verificationStatus") == "accepted"]
