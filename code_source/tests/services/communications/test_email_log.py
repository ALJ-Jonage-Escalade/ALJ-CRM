"""E-mail log service: recording never fails a send; a competition's history with its contact summary."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from domain.errors import NotFound
from services.communications import email_log
from services.communications.email_log import logged_recipient, record_send


def test_record_send_writes_one_entry(email_log_store):
    recipients = [logged_recipient("a@example.org", "Ana", 3), logged_recipient("b@example.org", "Bob", 4, "refusé"),
                  logged_recipient("club@alj.example")]
    assert record_send("competition_email", "coach@alj.example", recipients, "Rappel", "Relance", [7, 7]) is None
    (entry,) = email_log_store.entries
    assert (entry["kind"], entry["author"], entry["template"], entry["subject"]) == ("competition_email", "coach@alj.example", "Relance", "Rappel")
    assert (entry["competition_ids"], entry["member_ids"]) == ([7], [3, 4])
    assert [(r["email"], r["status"], r["error"]) for r in entry["recipients"]] == [
        ("a@example.org", "sent", None), ("b@example.org", "failed", "refusé"), ("club@alj.example", "sent", None)]
    assert entry["at"].endswith("+00:00")


def test_competition_history(email_log_store):
    competition = {"participants": [{"adherent_id": 3, "email": "a@example.org"}, {"adherent_id": 4, "email": "b@example.org"}]}
    record_send("competition_email", "coach@alj.example", [logged_recipient("a@example.org", "Ana", 3)], "Rappel", competition_ids=[7])
    record_send("member_email", "coach@alj.example", [logged_recipient("a@example.org", "Ana", 3)], "Autre")
    email_log_store.entries.append({**email_log_store.entries[0], "at": "2000-01-01T00:00:00+00:00", "subject": "Ancien"})
    with patch.object(email_log, "require_competition", return_value=competition):
        history = email_log.competition_history(7)
    assert [e["subject"] for e in history["entries"]] == ["Rappel", "Ancien"]  # newest first, other sends left out
    contacts = history["summary"]["competitors"]
    assert [(c["member_id"], c["last_sent_at"] is not None) for c in contacts] == [(3, True), (4, False)]


def test_unknown_competition():
    with patch.object(email_log, "require_competition", side_effect=NotFound("Compétition introuvable.")), pytest.raises(NotFound):
        email_log.competition_history(99)
