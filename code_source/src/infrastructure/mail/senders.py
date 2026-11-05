"""The club's e-mail addresses: the only place they are written (the Vue app reads them from /api/email-templates)."""

from __future__ import annotations

# Sender addresses: club domain or the configured sending account (EmailDispatchService.is_allowed_sender)
CLUB_SENDER_DOMAIN = "alj-escalade.fr"

# Default sender address of the e-mails (can be chosen and saved per template in the UI)
DEFAULT_SENDER_EMAIL = f"inscription@{CLUB_SENDER_DOMAIN}"

# Sender display name (shown in the "From" column of mail clients)
DEFAULT_SENDER_NAME = "Amicale Laïque Jonage - Inscriptions"

# The club's official contact address, shown to members (e-mail signature, certificate) and put in the FFME export
CLUB_CONTACT_EMAIL = f"contact@{CLUB_SENDER_DOMAIN}"

# Addresses offered in the template editor's sender field
SENDER_SUGGESTIONS = (
    DEFAULT_SENDER_EMAIL,
    CLUB_CONTACT_EMAIL,
    f"competitions@{CLUB_SENDER_DOMAIN}",
    f"admin@{CLUB_SENDER_DOMAIN}",
)
