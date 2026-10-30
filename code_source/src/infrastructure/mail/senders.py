"""The club's sender addresses: the only place they are written (the Vue app reads them from /api/email-templates)."""

from __future__ import annotations

# Sender addresses: club domain or the configured sending account (EmailDispatchService.is_allowed_sender)
CLUB_SENDER_DOMAIN = "alj-escalade.fr"

# Adresse d'expédition par défaut des e-mails (choisissable/sauvegardable dans l'IHM)
DEFAULT_SENDER_EMAIL = f"inscription@{CLUB_SENDER_DOMAIN}"

# Nom d'affichage de l'expéditeur (visible dans la colonne « De » des messageries)
DEFAULT_SENDER_NAME = "Amicale Laïque Jonage - Inscriptions"

# Addresses offered in the template editor's sender field
SENDER_SUGGESTIONS = (
    DEFAULT_SENDER_EMAIL,
    f"contact@{CLUB_SENDER_DOMAIN}",
    f"competitions@{CLUB_SENDER_DOMAIN}",
    f"admin@{CLUB_SENDER_DOMAIN}",
)
