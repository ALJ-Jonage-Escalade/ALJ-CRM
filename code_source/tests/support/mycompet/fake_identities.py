"""Invented identities of the fake MyCompet pages (no real person): see dev/make_mycompet_fixture.py.

Not made with Faker: realistic names can match real climbers. Each name pairs an invented surname with an
invented first name; clubs say they are fictional; licences start with FAKE_LICENCE_PREFIX, which no FFME
licence uses."""
from __future__ import annotations

import itertools
from typing import Iterator

FAKE_LICENCE_PREFIX = "99"  # + 5 digits: 7-digit numbers, real FFME licences are 6 digits
FAKE_SURNAMES = ("ZORBALT", "QUILLMERE", "VANTRUSK", "MORDEVIN", "TRASKELL", "BRUMQUIST", "OXLENDRE", "FENWOLDE",
                 "GRAVOLUN", "PRIMSKAR", "DULVANTH", "KESTRUME")
FAKE_FIRST_NAMES = ("Ylvane", "Corwick", "Talmira", "Odrien", "Pelisse", "Varnaby", "Elstrid", "Mirovan", "Zelvine",
                    "Taurin", "Quessa", "Brovan")
FAKE_CLUBS = ("CLUB FICTIF DES FALAISES IMAGINAIRES", "VERTICAL INVENTÉ ESCALADE (FICTIF)",
              "BLOC FANTÔME CLUB FICTIF", "GRIMPEURS DE NULLE-PART (FICTIF)")


def fake_names() -> Iterator[str]:
    """« SURNAME First-name » pairs, every combination once, then again."""
    pairs = [f"{surname} {first}" for first in FAKE_FIRST_NAMES for surname in FAKE_SURNAMES]
    return itertools.cycle(pairs)
