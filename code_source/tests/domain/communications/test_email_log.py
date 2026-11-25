"""Contact summary of a competition: each competitor's last contact."""

from __future__ import annotations

from typing import List, Optional

import pytest

from domain.communications.email_log import (
    Competitor,
    EmailKind,
    EmailLogEntry,
    LoggedRecipient,
    SendStatus,
    contact_summary,
    last_correction_requests,
    member_ids_of,
)

ALICE = Competitor(member_id=1, email="alice@example.org")
BOB = Competitor(member_id=2, email="parent@example.org")  # Alice's brother: same parent address
GUEST = Competitor(member_id=None, email="Guest@Example.org")


def recipient(member_id: Optional[int], email: str, status: SendStatus = "sent") -> LoggedRecipient:
    return LoggedRecipient(member_id=member_id, email=email, name="", status=status,
                           error="refusé" if status == "failed" else None)


def entry(at: str, *recipients: LoggedRecipient, kind: EmailKind = "competition_email",
          competition_ids: Optional[List[int]] = None, item_ids: Optional[List[int]] = None) -> EmailLogEntry:
    return EmailLogEntry(at=at, author="coach@alj.example", kind=kind, template="", subject="Rappel",
                         competition_ids=competition_ids or [7], member_ids=member_ids_of(recipients),
                         recipients=list(recipients), helloasso_order_refs=[], helloasso_item_ids=item_ids or [])


@pytest.mark.parametrize("entries, competitor, last_sent_at, last_failed", [
    pytest.param([], ALICE, None, False, id="never contacted"),
    pytest.param([entry("2026-11-01", recipient(1, "old@example.org"))], ALICE, "2026-11-01", False,
                 id="member id matches whatever the address sent to"),
    pytest.param([entry("2026-11-01", recipient(None, "guest@example.org"))], GUEST, "2026-11-01", False,
                 id="no member id: lower-cased e-mail"),
    pytest.param([entry("2026-11-01", recipient(None, "alice@example.org"))], ALICE, None, False,
                 id="member id known: the address alone does not match"),
    pytest.param([entry("2026-11-01", recipient(1, "a@x.org", "failed")), entry("2026-11-02", recipient(1, "a@x.org"))],
                 ALICE, "2026-11-02", False, id="failed then sent"),
    pytest.param([entry("2026-11-02", recipient(1, "a@x.org", "failed")), entry("2026-11-01", recipient(1, "a@x.org"))],
                 ALICE, "2026-11-01", True, id="sent then failed (entries in any order)"),
    pytest.param([entry("2026-11-01", recipient(1, "parent@example.org", "failed"), recipient(2, "parent@example.org"))],
                 BOB, "2026-11-01", False, id="siblings sharing an address: each tracked on its own"),
    pytest.param([entry("2026-11-01", recipient(1, "parent@example.org", "failed"), recipient(2, "parent@example.org"))],
                 Competitor(member_id=1, email="parent@example.org"), None, True, id="the sibling whose e-mail failed"),
    pytest.param([entry("2026-11-01", recipient(1, "a@x.org"), kind="competition_all_paid")], ALICE, None, False,
                 id="internal kind ignored"),
    pytest.param([entry("2026-11-01", recipient(1, "a@x.org"), kind="results_batch", competition_ids=[7, 8])], ALICE, None, False,
                 id="results batch covering several competitions ignored"),
])
def test_competitor_contact(entries, competitor, last_sent_at, last_failed):
    (contact,) = contact_summary(entries, [competitor])["competitors"]
    assert (contact["member_id"], contact["email"]) == (competitor["member_id"], competitor["email"])
    assert (contact["last_sent_at"], contact["last_failed"]) == (last_sent_at, last_failed)


def test_member_ids_each_once():
    assert member_ids_of([recipient(2, "b"), recipient(None, "club"), recipient(1, "a"), recipient(2, "b")]) == [2, 1]


def test_the_last_correction_request_of_a_registration_is_the_latest_that_reached_someone() -> None:
    entries = [
        entry("2026-09-02", recipient(None, "molly@terrier.example"), kind="correction_request", item_ids=[1, 2]),
        entry("2026-09-05", recipient(None, "molly@terrier.example", "failed"), kind="correction_request", item_ids=[1]),
        entry("2026-09-03", recipient(None, "molly@terrier.example"), kind="member_email", item_ids=[2]),
    ]

    assert last_correction_requests(entries) == {1: {"at": "2026-09-02", "author": "coach@alj.example"},
                                                 2: {"at": "2026-09-02", "author": "coach@alj.example"}}
