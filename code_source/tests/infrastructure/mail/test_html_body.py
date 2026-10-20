"""Tests du rendu HTML des corps d'e-mail (balises simples + liens externes)."""
import os
import random
import re
import sys
import time
import unittest

_test_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_src_dir = os.path.join(os.path.dirname(_test_dir), "src") if os.path.basename(_test_dir) == "tests" else _test_dir
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from infrastructure.mail.html_body import _link_html, _restore_links, text_to_html


def _restore_links_regex(escaped: str) -> str:
    """Former implementation, kept as the reference for _restore_links."""
    return re.sub(r'&lt;a href="([^"]*)"&gt;(.*?)&lt;/a&gt;',
                  lambda m: _link_html(m.group(1), m.group(2)), escaped, flags=re.S)


class TestTextToHtml(unittest.TestCase):
    def test_bold_italic_underline_preserved(self):
        out = text_to_html("Texte <b>gras</b>, <i>italique</i> et <u>souligné</u>.")
        self.assertIn("<b>gras</b>", out)
        self.assertIn("<i>italique</i>", out)
        self.assertIn("<u>soulignés</u>" if False else "<u>souligné</u>", out)

    def test_link_restored_with_href(self):
        out = text_to_html('Visitez <a href="https://www.exemple.fr">notre site</a> !')
        self.assertIn('<a href="https://www.exemple.fr" target="_blank" style="color:#2563EB;">notre site</a>', out)

    def test_mailto_link(self):
        out = text_to_html('<a href="mailto:contact@alj.fr">Écrivez-nous</a>')
        self.assertIn('<a href="mailto:contact@alj.fr"', out)

    def test_dangerous_scheme_neutralized(self):
        out = text_to_html('<a href="javascript:alert(1)">Cliquez</a>')
        self.assertNotIn("<a ", out)
        self.assertIn("Cliquez", out)

    def test_text_escaped_and_newlines(self):
        out = text_to_html("Ligne 1\n<b>Ligne 2</b>")
        self.assertIn("Ligne 1<br><b>Ligne 2</b>", out)

    def test_two_links_and_unclosed_one(self):
        out = text_to_html('<a href="https://a.fr">A</a> et <a href="https://b.fr">B</a> puis <a href="https://c.fr">C')
        self.assertIn('<a href="https://a.fr" target="_blank" style="color:#2563EB;">A</a>', out)
        self.assertIn('<a href="https://b.fr" target="_blank" style="color:#2563EB;">B</a>', out)
        self.assertIn('&lt;a href="https://c.fr"&gt;C', out)

    def test_restore_links_matches_former_regex(self):
        pieces = ['&lt;a href="', '"&gt;', "&lt;/a&gt;", '"', "https://x.fr", "mailto:a@b.fr", "javascript:x", "txt", "\n", " "]
        rng = random.Random(1234)
        for _ in range(3000):
            text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 12)))
            with self.subTest(text=text):
                self.assertEqual(_restore_links(text), _restore_links_regex(text))

    def test_many_unclosed_links_stay_fast(self):
        # Input reported by CodeQL (py/polynomial-redos): quadratic with the former regex
        text = '<a href="">' + '<a href="">a' * 20000
        started = time.perf_counter()
        text_to_html(text)
        self.assertLess(time.perf_counter() - started, 1.0)

    def test_variable_braces_not_swallowed(self):
        # Les variables {first_name}… ne contiennent pas de balise : elles restent telles quelles
        out = text_to_html("Bonjour {first_name}, épreuve {no_competition}.")
        self.assertIn("Bonjour {first_name}", out)
        self.assertIn("{no_competition}", out)


if __name__ == "__main__":
    unittest.main()
