"""Sending the club's e-mails: the MIME message is built here, then delivered through the Gmail API (club OAuth
account) or SMTP, with one audit line per send. Every failure is raised as MailError."""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import smtplib
import unicodedata
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import List, Optional, Sequence, Tuple

import requests

from domain.utils import sanitize_email_header
from infrastructure import runtime_env
from infrastructure.security.secret_store import SecretStore
from paths import DATA_ROOT

logger = logging.getLogger("alj")

SEND_TIMEOUT_SECONDS = 15


class MailError(RuntimeError):
    """An e-mail could not be sent: no valid configuration, unreadable inline image, Gmail API or SMTP failure."""


def _ascii_filename(name: str, fallback: str) -> str:
    """ASCII only: Gmail shows "noname" for an attachment whose name has accents."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii") or fallback


def build_message(to_email: str, subject: str, body: str, sender: str, sender_name: Optional[str] = None,
                  html_body: Optional[str] = None, inline_images: Optional[Sequence[Tuple[str, str]]] = None,
                  attachment_bytes: Optional[bytes] = None, attachment_filename: Optional[str] = None) -> MIMEMultipart:
    """The MIME message. Header values may come from member data: line breaks are removed so they cannot add
    headers. html_body: an HTML alternative to `body`, with inline images ((path, Content-ID) pairs);
    attachment_bytes: a file made in memory (PDF), never written to disk."""
    msg = MIMEMultipart()
    msg["Subject"] = sanitize_email_header(subject)
    msg["To"] = sanitize_email_header(to_email)
    name = sanitize_email_header(sender_name)
    msg["From"] = formataddr((name, sender)) if name else sender  # RFC 2822: readable name, accents encoded

    if html_body:
        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(body, "plain", "utf-8"))
        related = MIMEMultipart("related")
        related.attach(MIMEText(html_body, "html", "utf-8"))
        for image_path, content_id in inline_images or ():
            if not (image_path and os.path.exists(image_path)):
                continue
            try:
                with open(image_path, "rb") as image_file:
                    image = MIMEImage(image_file.read())
            except OSError as e:
                raise MailError(f"Image intégrée illisible : {os.path.basename(image_path)}") from e
            image.add_header("Content-ID", f"<{content_id}>")
            image.add_header("Content-Disposition", "inline", filename=os.path.basename(image_path))
            related.attach(image)
        alternative.attach(related)
        msg.attach(alternative)
    else:
        msg.attach(MIMEText(body, "plain"))

    if attachment_bytes and attachment_filename:
        filename = _ascii_filename(str(attachment_filename), "attestation.pdf")
        part = MIMEBase("application", "pdf" if filename.lower().endswith(".pdf") else "octet-stream")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)
    return msg


class EmailRepository:
    """Delivery of the messages and the audit log of the sends."""

    # Journal d'audit dans data/ : persistant, survit aux mises à jour de l'application
    AUDIT_FILE_PATH = os.path.join(DATA_ROOT, "email_audit.log")

    @classmethod
    def log_audit(cls, to_email: str, subject: str, status: str, error_message: str = "") -> None:
        """Enregistre un événement d'envoi de mail dans le journal d'audit."""
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "to": to_email,
            "subject": subject,
            "status": status,
            "error": error_message,
        }
        try:
            with open(cls.AUDIT_FILE_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Journal d'audit des e-mails non écrit (%s)", cls.AUDIT_FILE_PATH, exc_info=True)

    @classmethod
    def send_email(cls, to_email: str, subject: str, body: str, html_body: Optional[str] = None,
                   inline_images: Optional[Sequence[Tuple[str, str]]] = None, from_email: Optional[str] = None,
                   from_name: Optional[str] = None, attachment_bytes: Optional[bytes] = None,
                   attachment_filename: Optional[str] = None) -> None:
        """Sends one e-mail (`to_email`: one address, or several separated by commas) through the Gmail API when the
        club's OAuth account is configured, else SMTP. `from_email`: sender address (a verified alias of the
        account), the account itself by default; `from_name`: name shown in the "From" column.
        Raises MailError on any failure; the audit log records the outcome either way."""
        to_email = sanitize_email_header(to_email)  # may come from member data: no line break in the envelope
        gmail_user = SecretStore.get_secret("GMAIL_USER_EMAIL")
        use_gmail = bool(gmail_user and SecretStore.get_secret("GMAIL_CLIENT_ID") and SecretStore.get_secret("GMAIL_REFRESH_TOKEN"))
        smtp_user = SecretStore.get_secret("SMTP_USER")
        smtp_from = SecretStore.get_secret("SMTP_FROM_EMAIL") or smtp_user
        sender = sanitize_email_header(from_email) or (gmail_user if use_gmail else smtp_from)
        try:
            msg = build_message(to_email, subject, body, sender, from_name, html_body, inline_images,
                                attachment_bytes, attachment_filename)
            if use_gmail:
                cls._send_with_gmail(msg, gmail_user)
            else:
                cls._send_with_smtp(msg, to_email, smtp_user, smtp_from)
        except Exception as e:  # MailError, or any transport failure (network, smtplib, Google token)
            cls.log_audit(to_email, subject, "FAIL", str(e))
            if isinstance(e, MailError):
                raise
            raise MailError(f"Envoi de l'e-mail impossible : {type(e).__name__}: {e}") from e
        cls.log_audit(to_email, subject, "SUCCESS")

    @staticmethod
    def _send_with_gmail(msg: MIMEMultipart, gmail_user: str) -> None:
        """Gmail REST API (HTTPS) with the club's OAuth account."""
        from infrastructure.google.drive import GoogleDriveClient
        response = requests.post(
            f"https://gmail.googleapis.com/gmail/v1/users/{gmail_user}/messages/send",
            headers={"Authorization": f"Bearer {GoogleDriveClient.get_access_token()}", "Content-Type": "application/json"},
            json={"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")},
            timeout=SEND_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise MailError(f"API Gmail HTTP {response.status_code} - {response.text}")

    @staticmethod
    def _send_with_smtp(msg: MIMEMultipart, to_email: str, smtp_user: str, smtp_from: str) -> None:
        """SMTP: implicit TLS on port 465, else STARTTLS, required outside dev (Mailpit offers none). The envelope
        sender is the authenticated account (servers require it); the chosen address is in the "From" header."""
        host = SecretStore.get_secret("SMTP_HOST")
        password = SecretStore.get_secret("SMTP_PASSWORD")
        if not host or not smtp_user or not password:
            raise MailError("Aucune configuration d'envoi d'e-mails (Gmail OAuth2 ou SMTP classique) n'est valide.")
        port = int(SecretStore.get_secret("SMTP_PORT") or 587)
        server = smtplib.SMTP_SSL(host, port, timeout=SEND_TIMEOUT_SECONDS) if port == 465 else smtplib.SMTP(host, port, timeout=SEND_TIMEOUT_SECONDS)
        try:
            if port != 465:
                server.ehlo()
                if server.has_extn("starttls"):
                    server.starttls()  # a failure is raised: never fall back to cleartext once offered
                    server.ehlo()
                elif runtime_env.is_dev():
                    logger.info("STARTTLS non proposé par %s (Mailpit en dev) : envoi sans chiffrement", host)
                else:
                    # The password and the members' e-mails must never travel unencrypted
                    raise smtplib.SMTPNotSupportedError(f"STARTTLS non proposé par {host} : envoi refusé sans chiffrement")
            server.login(smtp_user, password)
            recipients: List[str] = [address.strip() for address in to_email.split(",") if address.strip()]
            server.sendmail(smtp_from, recipients, msg.as_string())
        finally:
            try:
                server.quit()
            except smtplib.SMTPException:
                server.close()
