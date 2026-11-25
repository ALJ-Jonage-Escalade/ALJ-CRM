"""infrastructure.helloasso.api.fetch_form_items: every page read through continuationToken, and a failure on any
page raised, never answered as a partial campaign."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.helloasso import api
from infrastructure.helloasso.api import HelloAssoApiError


def page(items: list[dict[str, Any]], next_page: str | None = None, status_code: int = 200) -> MagicMock:  # Any: HelloAsso JSON
    """A page of items; `next_page`: its continuationToken."""
    response = MagicMock(status_code=status_code)
    response.json.return_value = {"data": items, "pagination": {"continuationToken": next_page} if next_page else {}}
    return response


@pytest.fixture(autouse=True)
def credentials() -> Any:
    """Credentials configured and a token at hand: only the items calls go to `requests.get`."""
    with patch.object(api, "credentials_configured", return_value=True), \
         patch.object(api, "get_access_token", return_value="token"), \
         patch.object(api, "org_slug", return_value="club"):
        yield


def fetch(*responses: MagicMock) -> tuple[list[dict[str, Any]], list[str | None]]:  # Any: HelloAsso JSON
    """The items read and the continuationToken sent with each request (the params dict is reused between pages)."""
    pending, tokens_sent = list(responses), []

    def get(url: str, **kwargs: Any) -> MagicMock:  # Any: requests keyword arguments
        tokens_sent.append(kwargs["params"].get("continuationToken"))
        return pending.pop(0)

    with patch.object(api.requests, "get", side_effect=get):
        return api.fetch_form_items("Event", "competitions"), tokens_sent


def test_pages_are_read_until_an_empty_one() -> None:
    items, tokens_sent = fetch(page([{"id": 1}, {"id": 2}], next_page="t1"), page([{"id": 3}], next_page="t2"), page([]))
    assert [item["id"] for item in items] == [1, 2, 3]
    assert tokens_sent == [None, "t1", "t2"]


def test_a_page_without_a_token_is_the_last() -> None:
    items, tokens_sent = fetch(page([{"id": 1}]))
    assert [item["id"] for item in items] == [1]
    assert tokens_sent == [None]


def test_a_repeated_token_stops_the_loop() -> None:
    items, tokens_sent = fetch(page([{"id": 1}], next_page="same"), page([{"id": 2}], next_page="same"))
    assert [item["id"] for item in items] == [1, 2]
    assert tokens_sent == [None, "same"]


def test_a_server_error_on_a_later_page_is_raised_not_a_partial_list() -> None:
    with pytest.raises(HelloAssoApiError, match="HTTP 500"):
        fetch(page([{"id": 1}], next_page="t1"), page([], status_code=500))
