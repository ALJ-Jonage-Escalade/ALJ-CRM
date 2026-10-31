"""infrastructure.helloasso.api.list_forms: filters sent, every page read, errors raised (not an empty list)."""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.helloasso import api
from infrastructure.helloasso.api import HelloAssoApiError


def answer(status: int = 200, data: List[dict] | None = None, token: str | None = None) -> MagicMock:
    response = MagicMock(status_code=status)
    response.json.return_value = {"data": data or [], "pagination": {"continuationToken": token} if token else {}}
    return response


@pytest.fixture
def signed_in() -> Any:  # Any: the patchers
    with patch.object(api, "credentials_configured", return_value=True), \
            patch.object(api, "get_access_token", return_value="token"):
        yield


def test_list_forms_reads_every_page_with_the_filters(signed_in: None) -> None:
    pages = [answer(data=[{"formSlug": "a"}], token="t1"), answer(data=[{"formSlug": "b"}], token="t2"),  # noqa: S106 - pagination tokens
             answer(data=[])]
    sent: List[dict] = []

    def fake_get(url: str, headers: dict, params: dict, timeout: int) -> MagicMock:
        sent.append(dict(params))
        return pages[len(sent) - 1]

    with patch.object(api.requests, "get", side_effect=fake_get):
        forms = api.list_forms(["Membership", "Event"], ["Public", "Private"])
    assert [form["formSlug"] for form in forms] == ["a", "b"]
    assert sent[0] == {"formTypes": ["Membership", "Event"], "states": ["Public", "Private"], "pageSize": 100}
    assert [params.get("continuationToken") for params in sent] == [None, "t1", "t2"]


@pytest.mark.parametrize("behaviour", [
    {"side_effect": requests.exceptions.ConnectionError("down")},
    {"return_value": answer(status=500)},
])
def test_list_forms_raises_on_request_error(signed_in: None, behaviour: dict) -> None:
    with patch.object(api.requests, "get", **behaviour), pytest.raises(HelloAssoApiError):
        api.list_forms(["Event"], ["Public"])


def test_list_forms_raises_without_credentials() -> None:
    with patch.object(api, "credentials_configured", return_value=False), pytest.raises(HelloAssoApiError):
        api.list_forms(["Event"], ["Public"])


def test_list_forms_raises_without_token() -> None:
    with patch.object(api, "credentials_configured", return_value=True), patch.object(api, "get_access_token", return_value=None), \
            pytest.raises(HelloAssoApiError):
        api.list_forms(["Event"], ["Public"])
