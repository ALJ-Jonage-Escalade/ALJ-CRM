"""
Attestation PDF security: member data (public HelloAsso form) and request values must
never inject markup into the attestation HTML, and WeasyPrint must never read server
files or the network while rendering it.
"""

import os
import re
import sys
import unittest
import zlib

_tests_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from exports.attestation import (  # noqa: E402
    build_attestation,
    render_attestation_pdf,
)

INJECTION = '<a rel="attachment" href="file:///etc/hostname">x</a>'
CLUB_EMAIL = "club@alj.example"


def _weasyprint_available() -> bool:
    try:
        from weasyprint import HTML
        HTML(string="<p>x</p>").write_pdf()
        return True
    except Exception:
        return False


def _pdf_contains(pdf: bytes, needle: bytes) -> bool:
    """True if `needle` appears in the PDF, raw or inside a Flate-compressed stream."""
    if needle in pdf:
        return True
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            if needle in zlib.decompress(m.group(1)):
                return True
        except zlib.error:
            continue
    return False


class TestAttestationEscaping(unittest.TestCase):

    def test_member_and_request_values_are_escaped(self):
        member = {"first_name": INJECTION, "last_name": INJECTION, "payer": f"{INJECTION} {INJECTION}",
                  "amount": 150}
        html = build_attestation(member, season=INJECTION, date_jour=INJECTION, club_email=CLUB_EMAIL)
        self.assertNotIn('rel="attachment"', html.lower())
        self.assertNotIn("<a ", html.lower())
        self.assertIn("&lt;", html)

    def test_regular_names_unchanged(self):
        html = build_attestation({"first_name": "Hermione", "last_name": "Granger", "amount": 150},
                                 season="2026-2027", date_jour="1 September 2026", club_email=CLUB_EMAIL)
        self.assertIn("Hermione", html)
        self.assertIn("GRANGER", html)
        self.assertIn("150,00", html)

    def test_footer_shows_the_club_email(self):
        html = build_attestation({"first_name": "Hermione", "last_name": "Granger", "amount": 150}, club_email=CLUB_EMAIL)
        self.assertIn(f"Email : {CLUB_EMAIL} |", html)
        self.assertNotIn("{Email club}", html)


@unittest.skipUnless(_weasyprint_available(), "WeasyPrint (Pango) not available")
class TestAttestationRendering(unittest.TestCase):

    def test_local_files_are_never_embedded(self):
        """Even raw markup reaching the renderer cannot read a server file."""
        with open("/etc/hostname", "rb") as f:
            secret = f.read().strip()
        pdf = render_attestation_pdf(f"<p>{INJECTION}</p><img src='file:///etc/hostname'>")
        self.assertNotIn(b"/EmbeddedFile", pdf)
        self.assertFalse(_pdf_contains(pdf, secret))

    def test_renders_a_pdf(self):
        html = build_attestation({"first_name": "Alex", "last_name": "Martin", "amount": 195},
                                 season="2026-2027", club_email=CLUB_EMAIL)
        pdf = render_attestation_pdf(html)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 300)

    def test_embedded_images_still_rendered(self):
        html = build_attestation({"first_name": "Harry", "last_name": "Potter", "amount": 150},
                                 season="2026-2027", club_email=CLUB_EMAIL)
        if "data:image" not in html:
            self.skipTest("no logo or signature image available")
        pdf = render_attestation_pdf(html)
        self.assertIn(b"/Subtype /Image", pdf)


if __name__ == "__main__":
    unittest.main()
