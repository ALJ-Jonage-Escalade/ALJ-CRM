"""Invitations: the entry, the e-mail and its link, a send failure that keeps the invitation, the resend."""

from __future__ import annotations

from typing import Any

import pytest

from infrastructure.security.role_directory import RoleDirectory
from services.access import invitations
from services.access.rules import AccessRules
from domain.errors import Conflict
from infrastructure.mail.repository import MailError
from support.fake_access import FakeClock, InMemoryAccessStore, role_entry

ADMIN = "albus@alj.example"
GUEST = "neville@alj.example"
PAGE = "https://bureau.alj.example"


class FakeSender:
    """EmailRepository.send_email: records the e-mail, raises `failure` when given."""
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.sent: list[dict[str, Any]] = []  # Any: the keyword arguments of EmailRepository.send_email

    def __call__(self, **mail: Any) -> None:  # Any: as above
        self.sent.append(mail)
        if self.failure:
            raise self.failure


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> InMemoryAccessStore:
    store = InMemoryAccessStore()
    store.save_role(role_entry(ADMIN, "admin", "Albus Dumbledore"))
    return store


@pytest.fixture
def rules(store: InMemoryAccessStore, clock: FakeClock) -> AccessRules:
    return AccessRules(store, RoleDirectory(store, clock), clock)


@pytest.fixture(autouse=True)
def no_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)


def test_invite_sends_the_email(rules: AccessRules, store: InMemoryAccessStore) -> None:
    sender = FakeSender()
    invitation = invitations.invite(rules, ADMIN, GUEST, "coach", "Neville", PAGE, sender)
    assert (invitation["email_sent"], invitation["email_error"]) == (True, None)
    assert invitation["entry"]["invitation_sent_at"] == "2026-10-30T09:00:00+00:00"
    assert store.roles[GUEST]["invitation_sent_at"] == "2026-10-30T09:00:00+00:00"
    [mail] = sender.sent
    assert (mail["to_email"], mail["subject"]) == (GUEST, invitations.SUBJECT)
    text = mail["body"]
    assert text.startswith("Bonjour Neville,")
    assert "Albus Dumbledore vous invite" in text and "en tant que coach" in text
    assert f"{PAGE}/bureau/" in text
    assert f"l'adresse {GUEST}" in text and invitations.GOOGLE_SIGNUP_URL in text
    assert "valable jusqu'au 06/11/2026" in text
    assert f'href="{PAGE}/bureau/"' in mail["html_body"]


def test_link_from_app_public_url(rules: AccessRules, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PUBLIC_URL", "https://crm.alj.example/")
    sender = FakeSender()
    invitations.invite(rules, ADMIN, GUEST, "coach", "", PAGE, sender)
    assert "https://crm.alj.example/bureau/" in sender.sent[0]["body"]
    assert sender.sent[0]["body"].startswith("Bonjour,\n")


def test_html_is_escaped(rules: AccessRules) -> None:
    sender = FakeSender()
    invitations.invite(rules, ADMIN, GUEST, "readonly", "<b>Neville</b>", PAGE, sender)
    assert "&lt;b&gt;Neville&lt;/b&gt;" in sender.sent[0]["html_body"]
    assert "en tant que lecture seule" in sender.sent[0]["body"]


def test_inviter_without_name_shown_by_address(rules: AccessRules, store: InMemoryAccessStore) -> None:
    store.save_role(role_entry("minerva@alj.example", "admin"))
    sender = FakeSender()
    invitations.invite(rules, "minerva@alj.example", GUEST, "coach", "", PAGE, sender)
    assert "minerva@alj.example vous invite" in sender.sent[0]["body"]


@pytest.mark.parametrize("failure", [MailError("SMTP refusé"), ValueError("Aucune configuration d'envoi d'e-mails")])
def test_send_failure_keeps_the_invitation(rules: AccessRules, store: InMemoryAccessStore, failure: Exception) -> None:
    invitation = invitations.invite(rules, ADMIN, GUEST, "coach", "", PAGE, FakeSender(failure))
    assert invitation["email_sent"] is False
    assert invitation["email_error"]
    assert store.roles[GUEST]["invitation_sent_at"] is None
    assert store.roles[GUEST]["invitation_expires_at"] == "2026-11-06T09:00:00+00:00"


def test_refused_invitation_sends_nothing(rules: AccessRules) -> None:
    sender = FakeSender()
    with pytest.raises(Conflict):
        invitations.invite(rules, ADMIN, ADMIN, "coach", "", PAGE, sender)
    assert sender.sent == []


def test_resend_after_expiry(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    invitations.invite(rules, ADMIN, GUEST, "coach", "", PAGE, FakeSender(MailError("SMTP refusé")))
    clock.advance(days=8)
    sender = FakeSender()
    invitation = invitations.resend(rules, ADMIN, GUEST, PAGE, sender)
    assert invitation["email_sent"] is True
    assert invitation["entry"]["invitation_expires_at"] == "2026-11-14T09:00:00+00:00"
    assert "valable jusqu'au 14/11/2026" in sender.sent[0]["body"]
    assert [h["action"] for h in store.history] == ["invited", "invitation_resent"]


def test_expiry_date_in_paris_time(rules: AccessRules, clock: FakeClock) -> None:
    clock.advance(hours=14, minutes=30)  # 23:30 UTC: already the next day in Paris
    sender = FakeSender()
    invitations.invite(rules, ADMIN, GUEST, "coach", "", PAGE, sender)
    assert "valable jusqu'au 07/11/2026" in sender.sent[0]["body"]
