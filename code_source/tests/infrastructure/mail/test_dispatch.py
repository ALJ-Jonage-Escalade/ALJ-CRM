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

from infrastructure.mail.dispatch import EmailDispatchService
from api.communications.email import get_email_templates, preview_email, get_email_status


class TestEmailDispatchService(unittest.TestCase):
    """Vérifie la résolution des variables, l'aperçu et l'envoi d'e-mails."""

    def test_preview_with_variables(self):
        comp_ctx = {
            "name_competition": "Coupe Régionale Bugey",
            "no_competition": "18866",
            "montant_competition": "18,00 €",
            "date_competition": "03/10/2026",
            "whatapp_Id": "https://chat.whatsapp.com/testgroup"
        }
        recipient = {
            "first_name": "Éden",
            "last_name": "COCHE",
            "licence_ffme": "615830",
            "email": "eden.coche@example.com"
        }
        template_subj = "Convocation {name_competition} - {first_name}"
        template_body = "Bonjour {first_name} {last_name},\nTa sélection pour {name_competition} (#{no_competition}) est confirmée.\nMontant : {montant_competition}.\nGroupe WhatsApp : {whatapp_Id}"

        with patch.object(EmailDispatchService, "get_competition_context", return_value=comp_ctx):
            preview = EmailDispatchService.preview(
                subject=template_subj,
                body=template_body,
                recipient=recipient,
                competition_id=3,
                add_signature=False
            )

            self.assertIn("Convocation Coupe Régionale Bugey - Éden", preview["subject"])
            self.assertIn("Bonjour Éden COCHE", preview["body_plain"])
            self.assertIn("Coupe Régionale Bugey (#18866)", preview["body_plain"])
            self.assertIn("18,00 €", preview["body_plain"])
            self.assertIn("https://chat.whatsapp.com/testgroup", preview["body_plain"])
            self.assertIn("<div", preview["body_html"])

    def test_get_competition_context_includes_whatsapp_link(self):
        fake_doc = {
            "id": 12, "nom": "Coupe Bugey", "id_ffme": "12345", "prix": 15.0,
            "date_competition": "2026-10-03", "whatsapp_link": "https://chat.whatsapp.com/abc",
        }
        with patch("infrastructure.mail.dispatch.CompetitionRepository.get_competition_doc", return_value=fake_doc):
            ctx = EmailDispatchService.get_competition_context(12)
            self.assertEqual(ctx["whatapp_Id"], "https://chat.whatsapp.com/abc")
            self.assertEqual(ctx["whatsapp_link"], "https://chat.whatsapp.com/abc")
            self.assertEqual(ctx["name_competition"], "Coupe Bugey")

    def test_get_competition_context_includes_place(self):
        """The place is a pass-through field of the document (not in the domain model)."""
        fake_doc = {"id": 12, "nom": "Coupe Bugey", "lieu": " CUSSET "}
        with patch("infrastructure.mail.dispatch.CompetitionRepository.get_competition_doc", return_value=fake_doc):
            ctx = EmailDispatchService.get_competition_context(12)
            self.assertEqual(ctx["lieu"], "CUSSET")
            self.assertEqual(ctx["competition_lieu"], "CUSSET")

    @patch("infrastructure.mail.repository.EmailRepository.send_email")
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

    def test_fastapi_preview_and_templates_endpoints(self):
        """Teste les route handlers FastAPI /api/email-templates et /api/preview-email."""
        # 1. Templates
        res_t = get_email_templates()
        self.assertEqual(res_t.status, "success")
        template_names = [t.name for t in res_t.templates]
        self.assertIn("Compétition - 1er Inscription", template_names)
        self.assertIn("Compétition - relance", template_names)

        # 2. Preview
        preview_req = {
            "subject": "Test {first_name}",
            "body": "Bonjour {first_name}",
            "recipient": {"first_name": "Paul", "last_name": "NOEL"}
        }
        from api.communications.schemas import EmailPreviewRequest
        res_p = preview_email(EmailPreviewRequest.model_validate(preview_req))
        self.assertEqual(res_p.status, "success")
        self.assertEqual(res_p.preview.subject, "Test Paul")
        self.assertIn("Bonjour Paul", res_p.preview.body_plain)

        # 3. Email Status
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


if __name__ == "__main__":
    unittest.main()
