"""Allowed sender addresses: the sending account and its verified aliases, nothing else."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from domain.errors import Forbidden
from services.communications.senders import allowed_senders, resolve_sender

GMAIL_ENV = {"GMAIL_USER_EMAIL": "admin@alj-escalade.fr", "GMAIL_CLIENT_ID": "id", "GMAIL_REFRESH_TOKEN": "token"}


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("SMTP_USER", "dev")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "office@hogwarts.example")
    return monkeypatch


def test_smtp_allows_the_account_and_the_configured_aliases(smtp: pytest.MonkeyPatch) -> None:
    smtp.setenv("SMTP_SENDER_ALIASES", "Minerva@hogwarts.example, severus@hogwarts.example")
    senders = allowed_senders()
    assert senders["account"] == "office@hogwarts.example"
    assert senders["aliases"] == ["office@hogwarts.example", "minerva@hogwarts.example", "severus@hogwarts.example"]
    assert senders["error"] == ""


def test_smtp_without_aliases_allows_the_account_only(smtp: pytest.MonkeyPatch) -> None:
    assert allowed_senders()["aliases"] == ["office@hogwarts.example"]


def _gmail(monkeypatch: pytest.MonkeyPatch, status_code: int = 200, send_as: list | None = None) -> MagicMock:
    for key, value in GMAIL_ENV.items():
        monkeypatch.setenv(key, value)
    response = MagicMock(status_code=status_code)
    response.json.return_value = {"sendAs": send_as or []}
    monkeypatch.setattr("infrastructure.google.drive.GoogleDriveClient.get_access_token", lambda: "access")
    get = MagicMock(return_value=response)
    monkeypatch.setattr("infrastructure.mail.send_as.requests.get", get)
    return get


def test_gmail_allows_the_account_and_its_verified_aliases_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _gmail(monkeypatch, send_as=[
        {"sendAsEmail": "admin@alj-escalade.fr", "isPrimary": True},
        {"sendAsEmail": "inscription@alj-escalade.fr", "verificationStatus": "accepted"},
        {"sendAsEmail": "contact@alj-escalade.fr", "verificationStatus": "pending"},
    ])
    senders = allowed_senders()
    assert senders["account"] == "admin@alj-escalade.fr"
    assert senders["aliases"] == ["admin@alj-escalade.fr", "inscription@alj-escalade.fr"]


def test_gmail_refusal_allows_the_account_only_and_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    _gmail(monkeypatch, status_code=403)
    senders = allowed_senders()
    assert senders["aliases"] == ["admin@alj-escalade.fr"]
    assert "reconnectez le compte Google" in senders["error"]


def test_gmail_aliases_are_kept_five_minutes_but_a_failure_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    get = _gmail(monkeypatch, status_code=500)
    allowed_senders()
    allowed_senders()
    assert get.call_count == 2
    get.return_value.status_code = 200
    allowed_senders()
    allowed_senders()
    assert get.call_count == 3


def test_an_empty_sender_is_the_account(smtp: pytest.MonkeyPatch) -> None:
    assert resolve_sender("") == "office@hogwarts.example"
    assert resolve_sender(None) == "office@hogwarts.example"


def test_an_alias_is_sent_as_written_in_the_list(smtp: pytest.MonkeyPatch) -> None:
    smtp.setenv("SMTP_SENDER_ALIASES", "minerva@hogwarts.example")
    assert resolve_sender(" Minerva@Hogwarts.example ") == "minerva@hogwarts.example"


def test_another_address_is_refused_with_what_to_do(smtp: pytest.MonkeyPatch) -> None:
    with pytest.raises(Forbidden) as refused:
        resolve_sender("inscription@alj-escalade.fr")
    assert "inscription@alj-escalade.fr" in refused.value.message
    assert "office@hogwarts.example" in refused.value.message
