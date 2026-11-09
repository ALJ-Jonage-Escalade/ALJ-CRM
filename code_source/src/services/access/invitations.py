"""Invitations to the CRM (Administration › Accès): the entry through AccessRules, then the e-mail with the link.

The e-mail carries no token: the person gets the role by signing in with a Google account of the invited address
(role_directory). A send failure keeps the invitation (`invitation_sent_at` stays null): the admin resends it, or
tells the person another way. The template is fixed here, not in the editable e-mail templates, so the link and the
Google instruction can't be lost.
"""

from __future__ import annotations

import datetime
import logging
import os
from html import escape
from typing import Callable, Optional, TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from infrastructure.firestore.access_store import RoleEntry
from infrastructure.mail.repository import EmailRepository
from domain.club_emails import DEFAULT_SENDER_EMAIL, DEFAULT_SENDER_NAME
from infrastructure.security.role_directory import normalized_email, parsed
from services.access.rules import AccessRules

logger = logging.getLogger("alj")

APP_PATH = "/bureau/"
GOOGLE_SIGNUP_URL = "https://accounts.google.com/signup"
SUBJECT = "Invitation au bureau de la section escalade ALJ"
ROLE_LABELS = {"admin": "administrateur", "coach": "coach", "readonly": "lecture seule"}

# Sends one e-mail: EmailRepository.send_email (keyword arguments), a fake in the tests
Sender = Callable[..., None]  # EmailRepository.send_email: raises MailError on failure


class Invitation(TypedDict):
    entry: RoleEntry
    email_sent: bool
    email_error: Optional[str]


def app_link(page_url: str) -> str:
    """The office's address: APP_PUBLIC_URL (Cloud Run variable), else where the admin is using it."""
    base = os.environ.get("APP_PUBLIC_URL", "").strip() or page_url
    return f"{base.rstrip('/')}{APP_PATH}"


def _paris(at: datetime.datetime) -> datetime.datetime:
    try:
        return at.astimezone(ZoneInfo("Europe/Paris"))
    except ZoneInfoNotFoundError:  # no time zone database on this system: the UTC date, at most a day off
        return at


def expiry_date(entry: RoleEntry) -> str:
    """« 07/11/2026 », the last day the invitation can be accepted."""
    expires = parsed(entry["invitation_expires_at"])
    return _paris(expires).strftime("%d/%m/%Y") if expires else ""


def invitation_email(entry: RoleEntry, inviter: str, link: str) -> tuple[str, str]:
    """The text and HTML bodies of the invitation of this entry."""
    greeting = f"Bonjour {entry['display_name']}," if entry["display_name"] else "Bonjour,"
    role = ROLE_LABELS.get(entry["role"], entry["role"])
    email = entry["email"]
    until = expiry_date(entry)
    text = (
        f"{greeting}\n\n"
        f"{inviter} vous invite à accéder au bureau de la section escalade de l'Amicale Laïque de Jonage "
        f"en tant que {role}.\n\n"
        f"👉 {link}\n\n"
        f"Connectez-vous avec un compte Google utilisant l'adresse {email}. Si vous n'en avez pas, créez-en un avec "
        f"cette adresse, sans Gmail : {GOOGLE_SIGNUP_URL} (« Utiliser mon adresse e-mail actuelle »).\n\n"
        f"Cette invitation est valable jusqu'au {until}. Passé ce délai, demandez à un administrateur de la renvoyer.\n"
    )
    html = (
        f"<p>{escape(greeting)}</p>"
        f"<p>{escape(inviter)} vous invite à accéder au bureau de la section escalade de l'Amicale Laïque de Jonage "
        f"en tant que <b>{escape(role)}</b>.</p>"
        f'<p>👉 <a href="{escape(link)}">{escape(link)}</a></p>'
        f"<p>Connectez-vous avec un compte Google utilisant l'adresse <b>{escape(email)}</b>. Si vous n'en avez pas, "
        f'créez-en un avec cette adresse, sans Gmail : <a href="{GOOGLE_SIGNUP_URL}">{GOOGLE_SIGNUP_URL}</a> '
        f"(« Utiliser mon adresse e-mail actuelle »).</p>"
        f"<p>Cette invitation est valable jusqu'au <b>{escape(until)}</b>. Passé ce délai, demandez à un administrateur "
        f"de la renvoyer.</p>"
    )
    return text, html


def inviter_name(rules: AccessRules, author: str) -> str:
    """The admin's display name in the access list, else their address."""
    entry = rules.store.get_role(normalized_email(author))
    return entry["display_name"] if entry and entry["display_name"] else author


def send_invitation(rules: AccessRules, entry: RoleEntry, author: str, page_url: str,
                    send: Optional[Sender] = None) -> Invitation:
    """Sends the e-mail of this invitation (EmailRepository.send_email by default); a failure is reported, never raised."""
    send = send or EmailRepository.send_email
    try:
        text, html = invitation_email(entry, inviter_name(rules, author), app_link(page_url))
        send(to_email=entry["email"], subject=SUBJECT, body=text, html_body=html,
             from_email=DEFAULT_SENDER_EMAIL, from_name=DEFAULT_SENDER_NAME)
        return Invitation(entry=rules.mark_invitation_sent(entry["email"]), email_sent=True, email_error=None)
    except Exception as e:  # mailer down, bad configuration, store error after sending: the invitation stays
        logger.warning("Invitation de %s : e-mail non envoyé", entry["email"], exc_info=True)
        return Invitation(entry=entry, email_sent=False, email_error=str(e) or type(e).__name__)


def invite(rules: AccessRules, author: str, email: str, role: str, display_name: str, page_url: str,
           send: Optional[Sender] = None) -> Invitation:
    """Invites a new address (AccessRules.invite refusals raised), then e-mails it."""
    entry = rules.invite(author, email, role, display_name)
    return send_invitation(rules, entry, author, page_url, send)


def resend(rules: AccessRules, author: str, email: str, page_url: str,
           send: Optional[Sender] = None) -> Invitation:
    """A pending or expired invitation gets its full time again and its e-mail again."""
    entry = rules.renew_invitation(author, email)
    return send_invitation(rules, entry, author, page_url, send)
