"""The cases shared with the frontend's copy of the variables (frontend/src/lib/templateVariables.golden.json): the
server and the previews must give the same text."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from api.communications.email import get_email_variables
from domain.communications.email_personalization import template_values
from domain.communications.email_variables import render_html, render_template, template_error, to_keys, to_labels
from infrastructure.mail.html_body import text_to_html
from paths import CODE_ROOT

GOLDEN_PATH = Path(CODE_ROOT) / "frontend" / "src" / "lib" / "templateVariables.golden.json"
GOLDEN: dict[str, Any] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))  # Any: JSON


def test_the_variable_list_is_the_one_the_frontend_copies() -> None:
    assert [variable.model_dump() for variable in get_email_variables().variables] == GOLDEN["variables"]


@pytest.mark.parametrize("case", GOLDEN["render"], ids=lambda case: case["text"][:30])
def test_render_cases(case: dict[str, Any]) -> None:  # Any: JSON
    assert render_template(case["text"], case["values"], escape_html=case.get("html", False)) == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["html"], ids=lambda case: case["text"][:30])
def test_html_cases(case: dict[str, Any]) -> None:  # Any: JSON
    """The HTML part of the e-mail sent (without its frame and signature), as the previews show it."""
    assert render_html(case["text"], case["values"], text_to_html) == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["amounts"], ids=lambda case: str(case["amount"]))
def test_amount_cases(case: dict[str, Any]) -> None:  # Any: JSON
    assert template_values({"amount": case["amount"]})["amount"] == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["names"], ids=lambda case: case["first_name"])
def test_name_cases(case: dict[str, Any]) -> None:  # Any: JSON
    values = template_values({"first_name": case["first_name"], "last_name": case["last_name"]})
    assert [values["first_name"], values["last_name"]] == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["convert"], ids=lambda case: case["text"][:30])
def test_convert_cases(case: dict[str, Any]) -> None:  # Any: JSON
    assert (to_keys(case["text"]), to_labels(case["text"])) == (case["keys"], case["labels"])


@pytest.mark.parametrize("case", GOLDEN["errors"], ids=lambda case: case["texts"][0][:30])
def test_error_cases(case: dict[str, Any]) -> None:  # Any: JSON
    assert template_error(case["texts"], case.get("kind")) == case["expected"]
