"""infrastructure.helloasso.api.get_access_token: reused until shortly before it expires, dropped on a 401."""

from __future__ import annotations

from typing import Any, Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.helloasso import api
from infrastructure.helloasso.api import TOKEN_EXPIRY_MARGIN_SECONDS, HelloAssoApiError


def token_answer(token: str = "token", **fields: Any) -> MagicMock:  # noqa: S107 - fake token. Any: HelloAsso JSON
    response = MagicMock(status_code=200)
    response.json.return_value = {"access_token": token, **fields}
    return response


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Iterator[FakeClock]:
    """Credentials set and an empty token cache on a settable clock."""
    fake_clock = FakeClock()
    api._token_cache.invalidate()
    with patch.object(api, "CLIENT_ID", "id"), patch.object(api, "CLIENT_SECRET", "secret"), \
            patch.object(api._token_cache, "clock", fake_clock):
        yield fake_clock
    api._token_cache.invalidate()


def test_token_reused_until_shortly_before_it_expires(clock: FakeClock) -> None:
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)) as post:
        assert api.get_access_token() == "token"
        clock.now += 1800 - TOKEN_EXPIRY_MARGIN_SECONDS - 1
        assert api.get_access_token() == "token"
        assert post.call_count == 1
        clock.now += 1
        api.get_access_token()
        assert post.call_count == 2


@pytest.mark.parametrize("fields", [{}, {"expires_in": "1800"}, {"expires_in": TOKEN_EXPIRY_MARGIN_SECONDS}])
def test_token_without_a_usable_lifetime_is_not_kept(clock: FakeClock, fields: dict) -> None:
    with patch.object(api.requests, "post", return_value=token_answer(**fields)) as post:
        assert api.get_access_token() == "token"
        assert api.get_access_token() == "token"
    assert post.call_count == 2


def test_refused_authentication_gives_none_and_is_not_kept(clock: FakeClock) -> None:
    refused = MagicMock(status_code=401)
    refused.raise_for_status.side_effect = requests.exceptions.HTTPError("401")
    with patch.object(api.requests, "post", return_value=refused):
        assert api.get_access_token() is None
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)):
        assert api.get_access_token() == "token"


def test_answer_without_token_gives_none_and_is_not_kept(clock: FakeClock) -> None:
    answer = MagicMock(status_code=200)
    answer.json.return_value = {"expires_in": 1800}
    with patch.object(api.requests, "post", return_value=answer):
        assert api.get_access_token() is None
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)):
        assert api.get_access_token() == "token"


def test_no_credentials_no_token() -> None:
    with patch.object(api, "CLIENT_ID", None), patch.object(api.requests, "post") as post:
        assert api.get_access_token() is None
    post.assert_not_called()


def test_dev_mode_keeps_no_token(clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALJ_ENV", "dev")
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)) as post:
        api.get_access_token()
        api.get_access_token()
    assert post.call_count == 2


def refused_by(status: int) -> MagicMock:
    response = MagicMock(status_code=status)
    if status >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(str(status))
    return response


def quietly(call: Callable[[], Any]) -> None:  # Any: whatever the call answers
    """These calls report a refusal their own way: an empty list, None or HelloAssoApiError."""
    try:
        call()
    except HelloAssoApiError:
        pass


HELLOASSO_CALLS = {
    "get_campaigns": api.get_campaigns,
    "get_item": lambda: api.get_item(1),
    "list_forms": lambda: api.list_forms(["Event"], ["Public"]),
    "get_public_form": lambda: api.get_public_form("Event", "comp", api.require_access_token()),
    "fetch_form_items": lambda: api.fetch_form_items("Event", "comp"),
}


@pytest.mark.parametrize("call", HELLOASSO_CALLS.values(), ids=HELLOASSO_CALLS.keys())
def test_401_drops_the_token(clock: FakeClock, call: Callable[[], Any]) -> None:  # Any: whatever the call answers
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)) as post, \
            patch.object(api.requests, "get", return_value=refused_by(401)):
        quietly(call)
        assert post.call_count == 1
        api.get_access_token()
        assert post.call_count == 2


@pytest.mark.parametrize("status", [403, 500])
def test_other_errors_keep_the_token(clock: FakeClock, status: int) -> None:
    with patch.object(api.requests, "post", return_value=token_answer(expires_in=1800)) as post, \
            patch.object(api.requests, "get", return_value=refused_by(status)):
        quietly(lambda: api.list_forms(["Event"], ["Public"]))
        api.get_access_token()
    assert post.call_count == 1
