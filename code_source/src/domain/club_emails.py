"""The club's e-mail addresses: the only place they are written (the Vue app reads them from /api/email-templates)."""

from __future__ import annotations

# The club's mail domain. The sender addresses are not listed here: they are the sending account and its verified
# aliases (services.communications.senders)
CLUB_SENDER_DOMAIN = "alj-escalade.fr"

# Sender display name (shown in the "From" column of mail clients)
DEFAULT_SENDER_NAME = "Amicale Laïque Jonage - Inscriptions"

# The club's official contact address, shown to members (e-mail signature, certificate) and put in the FFME export
CLUB_CONTACT_EMAIL = f"contact@{CLUB_SENDER_DOMAIN}"
