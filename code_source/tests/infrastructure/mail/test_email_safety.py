"""
E-mails built from member data (public HelloAsso form): personalised values must
never add markup to the HTML part nor inject headers, while the template's own
formatting (<b>, links, line breaks) keeps working.
"""

import os
import sys
import unittest
from email import message_from_string
from unittest.mock import MagicMock, patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from domain.email_personalization import apply_template_variables  # noqa: E402
from infrastructure.mail.sender import sanitize_email_header  # noqa: E402
from services.communications.email_dispatch import EmailDispatchService  # noqa: E402
from support.fake_access import grant_roles  # noqa: E402

EVIL_NAME = '<a href="https://evil.example">Pay here</a>'


class TestPersonalisedHtml(unittest.TestCase):

    def _preview(self, body, first_name):
        with patch.object(EmailDispatchService, "get_competition_context", return_value={}):
            return EmailDispatchService.preview(
                subject="Hello {first_name}", body=body,
                recipient={"first_name": first_name, "last_name": "X", "email": "x@example.com"},
                add_signature=False)

    def test_member_value_cannot_add_markup(self):
        html = self._preview("Hello {first_name}", EVIL_NAME)["body_html"]
        self.assertNotIn("evil.example\"", html)
        self.assertNotIn("<a ", html)
        self.assertIn("&lt;a href=", html.lower())

    def test_template_formatting_still_works(self):
        html = self._preview('<b>Hello</b> {first_name}\n<a href="https://alj-escalade.fr">site</a>',
                             "Hermione")["body_html"]
        self.assertIn("<b>Hello</b> Hermione", html)
        self.assertIn('<a href="https://alj-escalade.fr"', html)
        self.assertIn("<br>", html)

    def test_plain_text_keeps_raw_value(self):
        self.assertEqual(self._preview("Hi {first_name}", "R&D")["body_plain"], "Hi R&D")

    def test_escape_option(self):
        member = {"first_name": "<b>x</b>", "last_name": "y"}
        self.assertEqual(apply_template_variables("{first_name}", member, escape_html=True), "&lt;B&gt;X&lt;/B&gt;")
        self.assertEqual(apply_template_variables("{first_name}", member), "<B>X</B>")

    def test_competition_deadline_variable(self):
        member = {"first_name": "Jean", "last_name": "DUPONT"}
        ctx = {"competition_deadline": "08/11/2026", "name_competition": "Coupe"}
        res = apply_template_variables("Date limite : {competition_deadline} pour {name_competition}", member, ctx)
        self.assertEqual(res, "Date limite : 08/11/2026 pour Coupe")


class TestHeaders(unittest.TestCase):

    def test_sanitize_email_header(self):
        self.assertEqual(sanitize_email_header("Hello\r\nBcc: evil@example.com"), "Hello Bcc: evil@example.com")
        self.assertEqual(sanitize_email_header(None), "")

    def test_smtp_message_has_no_injected_header(self):
        from infrastructure.mail.sender import EmailSender
        secrets = {"SMTP_HOST": "localhost", "SMTP_PORT": "1025", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
                   "SMTP_FROM_EMAIL": "office@example.com"}
        smtp = MagicMock()
        with patch("infrastructure.mail.sender.SecretStore.get_secret", side_effect=lambda k: secrets.get(k, "")), \
             patch("smtplib.SMTP", return_value=smtp), patch.object(EmailSender, "log_audit"):
            EmailSender.send_email(
                to_email="victim@example.com\r\nBcc: spy@example.com",
                subject="Hi\r\nBcc: spy@example.com", body="body",
                from_name="Club\r\nReply-To: spy@example.com")
        _, envelope_to, text = smtp.sendmail.call_args.args
        self.assertNotIn("\n", str(envelope_to))
        msg = message_from_string(text)
        self.assertIsNone(msg["Bcc"])
        self.assertIsNone(msg["Reply-To"])


class TestSmtpEncryption(unittest.TestCase):
    """The SMTP password and the members' e-mails never travel unencrypted, except to Mailpit in dev."""

    SECRETS = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p",
               "SMTP_FROM_EMAIL": "office@example.com"}

    def _send(self, smtp, dev=False):
        from infrastructure.mail.sender import EmailSender
        with patch("infrastructure.mail.sender.SecretStore.get_secret", side_effect=lambda k: self.SECRETS.get(k, "")), \
             patch("smtplib.SMTP", return_value=smtp), patch.object(EmailSender, "log_audit"), \
             patch("infrastructure.mail.sender.runtime_env.is_dev", return_value=dev):
            EmailSender.send_email(to_email="harry.potter@hogwarts.example", subject="s", body="b")

    def test_starttls_used_when_offered(self):
        smtp = MagicMock()
        smtp.has_extn.return_value = True
        self._send(smtp)
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once()

    def test_starttls_failure_is_raised_before_login(self):
        import smtplib
        from infrastructure.mail.sender import MailError
        smtp = MagicMock()
        smtp.has_extn.return_value = True
        smtp.starttls.side_effect = smtplib.SMTPException("handshake failed")
        with self.assertRaises(MailError):
            self._send(smtp)
        smtp.login.assert_not_called()
        smtp.sendmail.assert_not_called()

    def test_server_without_starttls_refused_in_production(self):
        from infrastructure.mail.sender import MailError
        smtp = MagicMock()
        smtp.has_extn.return_value = False
        with self.assertRaises(MailError) as raised:
            self._send(smtp)
        self.assertIn("STARTTLS", str(raised.exception))
        smtp.login.assert_not_called()

    def test_server_without_starttls_allowed_in_dev(self):
        smtp = MagicMock()
        smtp.has_extn.return_value = False
        self._send(smtp, dev=True)
        smtp.starttls.assert_not_called()
        smtp.sendmail.assert_called_once()


class TestGmailDelivery(unittest.TestCase):
    """With the club's OAuth account configured, e-mails go through the Gmail API, attachments included."""

    SECRETS = {"GMAIL_USER_EMAIL": "club@alj.example", "GMAIL_CLIENT_ID": "cid", "GMAIL_REFRESH_TOKEN": "refresh"}

    def _send(self, status_code=200):
        from infrastructure.mail.sender import EmailSender
        answer = MagicMock(status_code=status_code, text="quota exceeded")
        with patch("infrastructure.mail.sender.SecretStore.get_secret", side_effect=lambda k: self.SECRETS.get(k, "")), \
             patch("infrastructure.google.drive.GoogleDriveClient.get_access_token", return_value="access"), \
             patch("infrastructure.mail.sender.requests.post", return_value=answer) as post, \
             patch("smtplib.SMTP") as smtp, patch.object(EmailSender, "log_audit") as audit:
            EmailSender.send_email(to_email="harry.potter@hogwarts.example", subject="Attestation", body="Bonjour",
                                       html_body="<p>Bonjour</p>", attachment_bytes=b"%PDF-1.7",
                                       attachment_filename="Attestation Élève.pdf")
        smtp.assert_not_called()
        return post, audit

    def test_message_and_attachment_sent_through_gmail(self):
        import base64
        from email import message_from_bytes
        post, audit = self._send()
        url = post.call_args.args[0]
        self.assertTrue(url.endswith("/users/club@alj.example/messages/send"))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer access")
        msg = message_from_bytes(base64.urlsafe_b64decode(post.call_args.kwargs["json"]["raw"]))
        attachment = next(part for part in msg.walk() if part.get_content_disposition() == "attachment")
        self.assertEqual(attachment.get_filename(), "Attestation Eleve.pdf")  # ASCII: Gmail shows "noname" otherwise
        self.assertEqual(attachment.get_payload(decode=True), b"%PDF-1.7")
        self.assertEqual(audit.call_args.args[2], "SUCCESS")

    def test_gmail_refusal_is_a_mail_error(self):
        from infrastructure.mail.sender import MailError
        with self.assertRaises(MailError) as raised:
            self._send(status_code=429)
        self.assertIn("429", str(raised.exception))


class TestSendPermissions(unittest.TestCase):
    """A coach may only write to known members/payers; nobody may send as a foreign address."""

    KNOWN = {"harry.potter@hogwarts.example", "molly.weasley@hogwarts.example"}

    def setUp(self):
        patcher = patch.object(EmailDispatchService, "known_member_emails", return_value=self.KNOWN)
        patcher.start()
        self.addCleanup(patcher.stop)

    def reason(self, emails, sender=None, is_admin=False):
        return EmailDispatchService.unauthorized_send_reason(
            [{"email": e} for e in emails], sender, is_admin=is_admin)

    def test_coach_known_recipients(self):
        self.assertIsNone(self.reason(["Harry.Potter@hogwarts.example", "molly.weasley@hogwarts.example"]))

    def test_coach_unknown_recipient_refused(self):
        self.assertIn("spy@evil.example", self.reason(["harry.potter@hogwarts.example", "spy@evil.example"]))

    def test_admin_any_recipient(self):
        self.assertIsNone(self.reason(["anyone@example.com"], is_admin=True))

    def test_sender_allowlist(self):
        self.assertIsNone(self.reason([], sender="inscription@alj-escalade.fr"))
        self.assertIsNotNone(self.reason([], sender="president@evil.example", is_admin=True))


class TestSendEmailRoute(unittest.TestCase):

    def setUp(self):
        from fastapi.testclient import TestClient
        from server import app
        self.client = TestClient(app)

    def _send(self, claims, payload):
        grant_roles({"coach@example.com": "coach", "albus@alj-escalade.fr": "admin"})
        with patch.dict(os.environ, {"ALJ_API_AUTH": "required"}), \
             patch("infrastructure.security.api_auth.verify_firebase_token", return_value=claims), \
             patch.object(EmailDispatchService, "known_member_emails",
                          return_value={"harry.potter@hogwarts.example"}), \
             patch.object(EmailDispatchService, "dispatch_emails",
                          return_value={"status": "success", "sent_count": 1}) as dispatch:
            resp = self.client.post("/api/send-email", json=payload, headers={"Authorization": "Bearer t"})
        return resp, dispatch

    def test_coach_to_unknown_address_refused(self):
        coach = {"sub": "c", "email": "coach@example.com", "email_verified": True}
        resp, dispatch = self._send(coach, {"subject": "s", "body": "b",
                                            "recipients": [{"email": "spy@evil.example"}]})
        self.assertEqual(resp.status_code, 403)
        dispatch.assert_not_called()

    def test_coach_to_member_allowed(self):
        coach = {"sub": "c", "email": "coach@example.com", "email_verified": True}
        resp, dispatch = self._send(coach, {"subject": "s", "body": "b",
                                            "recipients": [{"email": "harry.potter@hogwarts.example"}]})
        self.assertEqual(resp.status_code, 200)
        dispatch.assert_called_once()

    def test_admin_to_any_address_allowed(self):
        admin = {"sub": "a", "email": "albus@alj-escalade.fr", "email_verified": True}
        resp, dispatch = self._send(admin, {"subject": "s", "body": "b",
                                            "recipients": [{"email": "partner@example.org"}]})
        self.assertEqual(resp.status_code, 200)
        dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
