"""api.auth.me.is_admin: the admin check of routes open to coaches with admin-only options."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import patch

import pytest

from api.auth import me
from domain.errors import StorageUnavailable
from infrastructure.security.api_auth import SCHEDULER_CLAIM
from infrastructure.security.role_directory import AccessUnavailable


def request_with(claims: Optional[dict[str, Any]]) -> Any:  # Any: stands in for a Starlette Request
    return SimpleNamespace(state=SimpleNamespace(user=claims))


def test_the_local_server_without_token_checks_is_admin() -> None:
    assert me.is_admin(request_with(None))


def test_cloud_scheduler_is_never_admin() -> None:
    with patch.object(me, "has_role", return_value=True):
        assert not me.is_admin(request_with({SCHEDULER_CLAIM: True}))


@pytest.mark.parametrize("listed_as_admin", [True, False])
def test_a_signed_in_account_gets_its_listed_role(listed_as_admin: bool) -> None:
    with patch.object(me, "has_role", return_value=listed_as_admin):
        assert me.is_admin(request_with({"email": "someone@example.org"})) is listed_as_admin


def test_an_unreadable_access_list_answers_503() -> None:
    with patch.object(me, "has_role", side_effect=AccessUnavailable("illisible")), pytest.raises(StorageUnavailable):
        me.is_admin(request_with({"email": "someone@example.org"}))
