"""
Tests unitaires pour le service d'expédition d'e-mails et les endpoints FastAPI associés.
"""

import os
import sys
import unittest
from unittest.mock import patch

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from domain.errors import InvalidRequest, UpstreamUnavailable
from infrastructure.mail.sender import MailError
from services.communications import email_log
from services.communications.email_dispatch import EmailDispatchService, render_email
from api.communications.email import get_email_templates, get_email_status
from infrastructure.sqlite.connection import _COMPETITION_EMAIL_TEMPLATES


class TestEmailDispatchService(unittest.TestCase):
    """Vérifie la résolution des variables, l'aperçu et l'envoi d'e-mails."""

    def test_render_with_variables(self):
        comp_ctx = {
            "name_competition": "Coupe Régionale Bugey",
            "no_competition": "18866",
            "montant_competition": "18,00 €",
            "date_competition": "03/10/2026",
            "whatsapp_link": "https://chat.whatsapp.com/testgroup"
        }
        recipient = {
            "first_name": "Éden",
            "last_name": "COCHE",
            "licence_ffme": "615830",
            "email": "eden.coche@example.com"
        }
        template_subj = "Convocation {name_competition} - {first_name}"
        template_body = "Bonjour {first_name} {last_name},\nTa sélection pour {name_competition} (#{no_competition}) est confirmée.\nMontant : {montant_competition}.\nGroupe WhatsApp : {whatapp_Id}"

        rendered = render_email(template_subj, template_body, recipient, comp_ctx, add_signature=False)
        self.assertIn("Convocation Coupe Régionale Bugey - Éden", rendered["subject"])
        self.assertIn("Bonjour Éden COCHE", rendered["body_plain"])
        self.assertIn("Coupe Régionale Bugey (#18866)", rendered["body_plain"])
        self.assertIn("18,00 €", rendered["body_plain"])
        self.assertIn("https://chat.whatsapp.com/testgroup", rendered["body_plain"])
        self.assertIn("<div", rendered["body_html"])

    def test_get_competition_context_includes_whatsapp_link(self):
        fake_doc = {
            "id": 12, "nom": "Coupe Bugey", "id_ffme": "12345", "prix": 15.0,
            "date_competition": "2026-10-03", "whatsapp_link": "https://chat.whatsapp.com/abc",
        }
        with patch("services.communications.email_dispatch.competitions.get_competition_doc", return_value=fake_doc):
            ctx = EmailDispatchService.get_competition_context(12)
            self.assertNotIn("whatapp_Id", ctx)
            self.assertEqual(ctx["whatsapp_link"], "https://chat.whatsapp.com/abc")
            self.assertEqual(ctx["name_competition"], "Coupe Bugey")

    @patch("infrastructure.mail.sender.EmailSender.send_email")
    def test_dispatch_emails_success(self, mock_send):
        mock_send.return_value = True

        recipients = [
            {"id": 1, "first_name": "Alice", "last_name": "DURAND", "email": "alice@example.com", "licence_ffme": "111111"},
            {"id": 2, "first_name": "Bob", "last_name": "LEFEVRE", "email": "bob@example.com", "licence_ffme": "222222"}
        ]

        res = EmailDispatchService.dispatch_emails(
            subject="Information {first_name}",
            body="Bonjour {first_name}, rappel licence {num_licence}.",
            recipients=recipients,
            add_signature=False
        )

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["sent_count"], 2)
        self.assertEqual(res["errors_count"], 0)
        self.assertEqual(mock_send.call_count, 2)

    @patch("services.communications.email_dispatch.EmailDispatchService.get_competition_context", return_value={})
    @patch("infrastructure.mail.sender.EmailSender.send_email")
    def test_dispatch_records_one_log_entry(self, mock_send, _context):
        """One send, one entry: each recipient with the address used and its own status, a partial failure included."""
        mock_send.side_effect = [None, MailError("550 mailbox unavailable")]
        recipients = [
            {"id": 1, "first_name": "Alice", "last_name": "DURAND", "email": "alice@example.com"},
            {"id": 2, "first_name": "Bob", "last_name": "DURAND", "email": "bob@example.com"},
            {"id": 3, "first_name": "Carl", "last_name": "SANS", "email": "pas-une-adresse"},
        ]
        res = EmailDispatchService.dispatch_emails(subject="Rappel {first_name}", body="Bonjour", recipients=recipients,
                                                   competition_id=7, add_signature=False, author="coach@alj.example")
        self.assertEqual((res["status"], res["log_notice"]), ("partial", None))
        (entry,) = email_log.current_store().entries
        self.assertEqual((entry["kind"], entry["author"], entry["competition_ids"], entry["member_ids"]),
                         ("competition_email", "coach@alj.example", [7], [1, 2]))
        self.assertEqual(entry["subject"], "Rappel Alice")
        self.assertEqual([(r["member_id"], r["email"], r["status"]) for r in entry["recipients"]],
                         [(1, "alice@example.com", "sent"), (2, "bob@example.com", "failed")])
        self.assertNotIn("550", entry["recipients"][1]["error"])  # the mailer's reason stays in the logs

    @patch("infrastructure.mail.sender.EmailSender.send_email", side_effect=MailError("down"))
    def test_dispatch_all_failed_is_recorded(self, _send):
        with self.assertRaises(UpstreamUnavailable):
            EmailDispatchService.dispatch_emails(subject="Info", body="Bonjour", recipients=[{"id": 1, "email": "a@example.com"}],
                                                 add_signature=False)
        (entry,) = email_log.current_store().entries
        self.assertEqual((entry["kind"], [r["status"] for r in entry["recipients"]]), ("member_email", ["failed"]))

    @patch("infrastructure.mail.sender.EmailSender.send_email")
    def test_dispatch_log_down_still_sent(self, _send):
        email_log.current_store().failing = True
        res = EmailDispatchService.dispatch_emails(subject="Info", body="Bonjour", recipients=[{"id": 1, "email": "a@example.com"}],
                                                   add_signature=False)
        self.assertEqual((res["status"], res["sent_count"], res["log_notice"]), ("success", 1, email_log.NOT_RECORDED))

    def test_fastapi_templates_and_status_endpoints(self):
        """Teste les route handlers FastAPI /api/email-templates et /api/email-status."""
        # 1. Templates
        res_t = get_email_templates()
        self.assertEqual(res_t.status, "success")
        template_names = [t.name for t in res_t.templates]
        self.assertIn("Compétition - 1er Inscription", template_names)
        self.assertIn("Compétition - relance", template_names)

        # 2. Email Status
        res_st = get_email_status()
        self.assertEqual(res_st.status, "success")
        self.assertIn(res_st.mode, ("gmail_oauth2", "smtp", "none"))

    def test_email_status_modes(self):
        """Gmail API first, then SMTP; nothing configured answers mode "none" and no sender."""
        gmail = {"GMAIL_USER_EMAIL": "club@example.org", "GMAIL_CLIENT_ID": "id", "GMAIL_REFRESH_TOKEN": "token"}
        smtp = {"SMTP_HOST": "smtp.example.org", "SMTP_USER": "relay@example.org", "SMTP_PASSWORD": "pw"}
        cases = [
            ({**gmail, **smtp}, True, "gmail_oauth2", "club@example.org"),
            (smtp, True, "smtp", "relay@example.org"),
            ({**smtp, "SMTP_PASSWORD": ""}, False, "none", ""),
            ({}, False, "none", ""),
        ]
        for secrets, configured, mode, sender in cases:
            with self.subTest(mode=mode, keys=sorted(secrets)), \
                    patch("api.communications.email.SecretStore.get_secret", side_effect=lambda key, s=secrets: s.get(key, "")):
                status = get_email_status()
                self.assertEqual((status.configured, status.mode, status.sender), (configured, mode, sender))


DISPATCH = "services.communications.email_dispatch"


@patch("infrastructure.mail.sender.EmailSender.send_email")
class TestEmailDispatchInputs(unittest.TestCase):
    """Recipients from member ids, template defaults and the requests refused before any send."""

    def test_recipient_ids_use_the_members_database_then_the_competition_directory(self, mock_send):
        members = {1: {"first_name": "Alice", "last_name": "DURAND", "email_primary": "",
                       "email_secondary": " alice@example.com ", "licence_ffme": None},
                   3: {"first_name": "Carl", "last_name": "SANS", "email_primary": None, "email_secondary": None,
                       "licence_ffme": ""}}
        directory = [{"id": 2, "prenom": "Bob", "nom": "LEFEVRE", "email": "bob@example.com", "num_licence": "222"}]
        with patch(f"{DISPATCH}.MemberRepository.get_users_by_ids", return_value=members), \
                patch(f"{DISPATCH}.member_directory.list_members", return_value=directory):
            res = EmailDispatchService.dispatch_emails(subject="Info", body="Licence {num_licence}",
                                                       recipient_ids=[1, 2, 3, 4], add_signature=False)
        self.assertEqual([(d["id"], d["email"], d["status"]) for d in res["details"]],
                         [(1, "alice@example.com", "sent"), (2, "bob@example.com", "sent"), (3, "", "error")])
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(mock_send.call_args.kwargs["body"], "Licence 222")

    def test_template_fills_the_fields_left_empty(self, mock_send):
        template = {"name": "Relance Compétition", "subject": "Relance {first_name}", "body": "Bonjour",
                    "sender_email": "bureau@example.org", "sender_name": "Bureau"}
        with patch.object(EmailDispatchService, "list_templates", return_value=[template]):
            EmailDispatchService.dispatch_emails(template_name="relance competition", body="Message propre",
                                                 recipients=[{"first_name": "Alice", "email": "a@example.com"}],
                                                 add_signature=False)
        sent = mock_send.call_args.kwargs
        self.assertEqual((sent["subject"], sent["body"]), ("Relance Alice", "Message propre"))
        self.assertEqual((sent["from_email"], sent["from_name"]), ("bureau@example.org", "Bureau"))

    def test_member_e_mail_fills_group_season_and_amount(self, mock_send):
        recipient = {"first_name": "alice", "email": "a@example.com", "tarif": "Ados", "season": "2026-2027", "amount": "195.5"}
        EmailDispatchService.dispatch_emails(subject="Rappel", body="{tarif} {season} : {amount} €", recipients=[recipient],
                                             add_signature=False)
        self.assertEqual(mock_send.call_args.kwargs["body"], "Ados 2026-2027 : 195,50 €")

    def test_shipped_competition_templates_leave_no_raw_token(self, mock_send):
        competition = {"name_competition": "Coupe", "no_competition": "42", "date_competition": "15/11/2026",
                       "montant_competition": "15", "whatsapp_link": ""}
        for _name, subject, body, *_sender in _COMPETITION_EMAIL_TEMPLATES:
            with self.subTest(template=_name), patch.object(EmailDispatchService, "get_competition_context", return_value=competition):
                EmailDispatchService.dispatch_emails(subject=subject, body=body, competition_id=7, add_signature=False,
                                                     recipients=[{"first_name": "alice", "email": "a@example.com"}])
                sent = mock_send.call_args.kwargs
                self.assertNotRegex(sent["subject"] + sent["body"] + sent["html_body"], r"\{[^{}<>\"\n]+\}")
                self.assertNotIn("WhatsApp", sent["body"])

    def test_unknown_template_and_no_subject_is_refused(self, mock_send):
        with patch.object(EmailDispatchService, "list_templates", return_value=[]), self.assertRaises(InvalidRequest):
            EmailDispatchService.dispatch_emails(template_name="Absent", body="Bonjour", recipients=[{"email": "a@example.com"}])
        mock_send.assert_not_called()

    def test_no_recipient_with_an_address_is_refused(self, mock_send):
        with self.assertRaises(InvalidRequest):
            EmailDispatchService.dispatch_emails(subject="Info", body="Bonjour", recipients=[{"email": "sans-arobase"}])
        mock_send.assert_not_called()

    def test_unknown_competition_gives_no_variables(self, _send):
        with patch(f"{DISPATCH}.competitions.get_competition_doc", return_value=None):
            self.assertEqual(EmailDispatchService.get_competition_context(99), {})


class TestKnownMemberEmails(unittest.TestCase):
    """Addresses a coach may write to: the members database and the competition directory, lower-cased."""

    def test_members_and_directory_are_merged(self):
        with patch(f"{DISPATCH}.MemberRepository.list_contact_emails", return_value={"alice@example.com"}), \
                patch(f"{DISPATCH}.member_directory.list_members", return_value=[{"email": " Bob@Example.com "}, {}]):
            self.assertEqual(EmailDispatchService.known_member_emails(), {"alice@example.com", "bob@example.com"})

    def test_directory_down_keeps_the_members_database(self):
        with patch(f"{DISPATCH}.MemberRepository.list_contact_emails", return_value={"alice@example.com"}), \
                patch(f"{DISPATCH}.member_directory.list_members", side_effect=ConnectionError("Firestore down")):
            self.assertEqual(EmailDispatchService.known_member_emails(), {"alice@example.com"})


if __name__ == "__main__":
    unittest.main()
