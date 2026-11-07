"""
Turns a MyCompet results page saved by hand into the anonymized template of the tests
(tests/support/mycompet/results_template.html), used by the unit tests and the fake MyCompet.

    uv run python dev/make_mycompet_fixture.py ../scripts_temporaires/mycompet/resultat_XXXX.html

A real page lists every climber of each category (name, club, licence number in the
`palmares_<licence>` link), many of them minors: save it OUTSIDE the repository
(scripts_temporaires/ is git-ignored). Only the layout is kept: every climber gets an invented
name and club and a licence in FAKE_LICENCE_PREFIX (no real licence starts with it); the title
and venue become placeholders; scripts, menus, external links and internal ids are dropped.
tests/infrastructure/mycompet/test_fake_pages.py checks the result. Read the generated file
once before committing it.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import os
import re
import sys

import lxml.html

CODE_SOURCE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(CODE_SOURCE, "tests"))

from support.mycompet.fake_identities import FAKE_CLUBS, FAKE_LICENCE_PREFIX, fake_names  # noqa: E402

DEFAULT_OUTPUT = os.path.join(CODE_SOURCE, "tests", "support", "mycompet", "results_template.html")


def anonymize(html_text: str, categories: int, rows_per_category: int) -> str:
    doc = lxml.html.fromstring(html_text)
    found = doc.xpath("//div[@id='main-content']")
    if not found:
        raise SystemExit("No <div id='main-content'>: is it a MyCompet results page?")
    main = copy.deepcopy(found[0])

    for element in main.xpath(".//*[contains(@class, 'filter-container') or contains(@class, 'status')]"):
        element.getparent().remove(element)
    subtitle = main.xpath(".//div[contains(@class, 'subtitle')]")
    if not subtitle:
        raise SystemExit("No subtitle (competition name): unexpected layout")
    subtitle[0].text = "{{TITLE}} - {{VENUE}}"
    for child in list(subtitle[0]):
        subtitle[0].remove(child)

    groups = main.xpath(".//div[contains(concat(' ', @class, ' '), ' regroupement ')]")
    if not groups:
        raise SystemExit("No result category (div.regroupement): unexpected layout")
    for group in groups[categories:]:
        group.getparent().remove(group)

    names = fake_names()
    clubs = itertools.cycle(FAKE_CLUBS)
    licences = itertools.count(1)
    row_ids = itertools.count(1)
    for index, group in enumerate(groups[:categories], start=1):
        for element in group.xpath(".//*[@id]"):
            # internal ids (U13_FEMME_15933): keep the category part only
            element.attrib["id"] = re.sub(r"\d{3,}", str(index), element.attrib["id"])
        rows = group.xpath(".//tr[.//a[contains(@href, 'palmares')]]")
        for row in rows[rows_per_category:]:
            row.getparent().remove(row)
        for row in rows[:rows_per_category]:
            row_id = next(row_ids)
            row.attrib["id"] = f"Q{row_id}"
            link = row.xpath(".//a[contains(@href, 'palmares')]")[0]
            link.attrib["href"] = f"palmares_{FAKE_LICENCE_PREFIX}{next(licences):05d}.html"
            for span in link.xpath(".//span[@id]"):
                span.attrib["id"] = f"P{row_id}"
            strong = link.xpath(".//strong")
            if not strong:
                raise SystemExit("A climber row has no <strong> name: unexpected layout")
            strong[0].text = next(names)
            for br in link.xpath(".//br"):
                br.tail = next(clubs)

    for element in main.iter():
        for attribute in [a for a in element.attrib if a.startswith("on") or a == "text-align:left"]:
            del element.attrib[attribute]
    for comment in main.xpath("//comment()"):
        comment.getparent().remove(comment)
    for link in main.xpath(".//a[@href]"):
        if not link.attrib["href"].startswith("palmares_"):
            raise SystemExit(f"Unexpected link left in the results: {link.attrib['href']}")

    body = lxml.html.tostring(main, encoding="unicode")
    return ("<!DOCTYPE html>\n<!-- Anonymized MyCompet layout (dev/make_mycompet_fixture.py): every name, club and licence\n"
            "     is invented; club athletes are added by tests/support/mycompet/render.py -->\n"
            "<html><head><meta charset=\"UTF-8\"><title>MyCompet</title></head>\n<body>\n" + body + "\n</body></html>\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("saved_page", help="MyCompet results page saved by hand (outside the repository)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--categories", type=int, default=3, help="categories kept (default 3)")
    parser.add_argument("--rows", type=int, default=8, help="climbers kept per category (default 8)")
    args = parser.parse_args()
    if os.path.commonpath([os.path.abspath(args.saved_page), CODE_SOURCE]) == CODE_SOURCE:
        print("⚠️  The saved page is inside code_source/: move it to scripts_temporaires/ (personal data).", file=sys.stderr)
    with open(args.saved_page, encoding="utf-8") as source:
        template = anonymize(source.read(), args.categories, args.rows)
    with open(args.output, "w", encoding="utf-8") as target:
        target.write(template)
    print(f"✅ {args.output} written: read it once before committing it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
