"""Routes of Administration › Accès (/api/admin/access) and what /api/me does with invitations, token checks on."""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from server import app
from support.fake_access import FakeClock, InMemoryAccessStore, install_access, role_entry

ADMIN = "albus@alj.example"
COACH = "severus@alj.example"
READONLY = "argus@alj.example"
STRANGER = "draco@alj.example"
BASE = "/api/admin/access"


@pytest.fixture
def store() -> InMemoryAccessStore:
    store = InMemoryAccessStore()
    for email, role in ((ADMIN, "admin"), (COACH, "coach"), (READONLY, "readonly")):
        store.save_role(role_entry(email, role))
    return store


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sent() -> MagicMock:
    """The invitation e-mails: EmailSender.send_email, faked."""
    return MagicMock(return_value=None)


@pytest.fixture
def client(store: InMemoryAccessStore, clock: FakeClock, sent: MagicMock, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    install_access(store, clock)
    monkeypatch.setenv("ALJ_API_AUTH", "required")
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    # The token's claims: the e-mail is the bearer token itself (signatures are tested in test_api_security)
    with patch("infrastructure.security.api_auth.verify_firebase_token",
               side_effect=lambda token: {"sub": token, "email": token, "email_verified": True, "name": "Google Name"}), \
         patch("services.access.invitations.EmailSender.send_email", sent):
        yield TestClient(app)


def me(client: TestClient, who: str) -> Any:  # Any: the JSON body
    return client.get("/api/me", headers={"Authorization": f"Bearer {who}"}).json()


def call(client: TestClient, method: str, path: str, who: str = ADMIN, **body: Any) -> Any:  # Any: JSON bodies
    return client.request(method, BASE + path, headers={"Authorization": f"Bearer {who}"}, json=body or None)


ROUTES = [("GET", "/roles"), ("POST", "/roles"), ("PATCH", f"/roles/{COACH}"), ("DELETE", f"/roles/{COACH}"),
          ("POST", f"/roles/{COACH}/invitation"), ("GET", "/history")]


@pytest.mark.parametrize("method, path", ROUTES)
@pytest.mark.parametrize("who", [COACH, READONLY, STRANGER])
def test_admin_only(client: TestClient, store: InMemoryAccessStore, method: str, path: str, who: str) -> None:
    r = call(client, method, path, who, email="x@alj.example", role="coach")
    assert r.status_code == 403
    assert store.history == []


@pytest.mark.parametrize("method, path", ROUTES)
def test_sign_in_required(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, BASE + path).status_code == 401


def test_list(client: TestClient) -> None:
    r = call(client, "GET", "/roles")
    assert r.status_code == 200
    assert [(e["email"], e["role"]) for e in r.json()] == [(ADMIN, "admin"), (READONLY, "readonly"), (COACH, "coach")]
    assert set(r.json()[0]) == {"email", "role", "display_name", "last_sign_in_at", "created_at", "created_by",
                                "updated_at", "updated_by", "invited_at", "invitation_expires_at", "invitation_sent_at",
                                "accepted_at"}


def test_invite_then_the_person_signs_in(client: TestClient, store: InMemoryAccessStore, sent: MagicMock, clock: FakeClock) -> None:
    r = client.post(BASE + "/roles", headers={"Authorization": f"Bearer {ADMIN}", "Origin": "http://localhost:5173"},
                    json={"email": " Neville@ALJ.example ", "role": "coach", "display_name": "Neville"})
    assert r.status_code == 201
    entry = r.json()["entry"]
    assert (entry["email"], entry["role"], entry["created_by"]) == ("neville@alj.example", "coach", ADMIN)
    assert (r.json()["email_sent"], r.json()["email_error"]) == (True, None)
    assert entry["invitation_sent_at"] == "2026-10-30T09:00:00+00:00"
    assert sent.call_args.kwargs["to_email"] == "neville@alj.example"
    assert "http://localhost:5173/bureau/" in sent.call_args.kwargs["body"]  # the admin's page, without APP_PUBLIC_URL
    clock.advance(days=6)
    assert me(client, "neville@alj.example") == {"email": "neville@alj.example", "role": "coach", "invitation_expired_at": None}
    assert store.roles["neville@alj.example"]["invitation_expires_at"] is None  # accepted: never expires now
    assert store.roles["neville@alj.example"]["accepted_at"] == "2026-11-05T09:00:00+00:00"
    clock.advance(days=30)
    assert me(client, "neville@alj.example")["role"] == "coach"


def test_invitation_expired(client: TestClient, clock: FakeClock) -> None:
    call(client, "POST", "/roles", email="neville@alj.example", role="coach")
    clock.advance(days=7)
    assert me(client, "neville@alj.example") == {"email": "neville@alj.example", "role": None,
                                                  "invitation_expired_at": "2026-11-06T09:00:00+00:00"}
    r = call(client, "POST", "/roles/neville@alj.example/invitation")
    assert r.status_code == 200
    assert r.json()["entry"]["invitation_expires_at"] == "2026-11-13T09:00:00+00:00"
    assert me(client, "neville@alj.example")["role"] == "coach"


def test_invitation_email_failure(client: TestClient, store: InMemoryAccessStore, sent: MagicMock) -> None:
    sent.side_effect = ValueError("Aucune configuration d'envoi d'e-mails")
    r = call(client, "POST", "/roles", email="neville@alj.example", role="coach")
    assert r.status_code == 201
    assert (r.json()["email_sent"], r.json()["email_error"]) == (False, "Aucune configuration d'envoi d'e-mails")
    assert store.roles["neville@alj.example"]["invitation_sent_at"] is None


def test_resend_refused_for_an_accepted_access(client: TestClient, sent: MagicMock) -> None:
    r = call(client, "POST", f"/roles/{COACH}/invitation")
    assert (r.status_code, r.json()["code"]) == (409, "not_invited")
    assert call(client, "POST", f"/roles/{STRANGER}/invitation").status_code == 404
    sent.assert_not_called()


def test_add_refusals(client: TestClient) -> None:
    r = call(client, "POST", "/roles", email="pas-une-adresse", role="coach")
    assert r.status_code == 400
    assert "invalide" in r.json()["message"]
    r = call(client, "POST", "/roles", email=COACH.upper(), role="admin")
    assert (r.status_code, r.json()["code"]) == (409, "already_listed")
    call(client, "POST", "/roles", email="neville@alj.example", role="coach")
    r = call(client, "POST", "/roles", email="neville@alj.example", role="coach")
    assert (r.status_code, r.json()["code"]) == (409, "already_invited")
    assert call(client, "POST", "/roles", email=STRANGER, role="owner").status_code == 422


def test_patch_role_and_name(client: TestClient, store: InMemoryAccessStore) -> None:
    r = call(client, "PATCH", f"/roles/{COACH}", role="admin", display_name="Prof. Rogue")
    assert r.status_code == 200
    assert (r.json()["role"], r.json()["display_name"]) == ("admin", "Prof. Rogue")
    assert [h["action"] for h in store.history] == ["role_changed", "name_changed"]
    assert call(client, "PATCH", f"/roles/{STRANGER}", role="coach").status_code == 404


def test_safeguards(client: TestClient, store: InMemoryAccessStore) -> None:
    r = call(client, "PATCH", f"/roles/{ADMIN}", role="coach")
    assert (r.status_code, r.json()["code"]) == (409, "self_demotion")
    r = call(client, "DELETE", f"/roles/{ADMIN}")
    assert (r.status_code, r.json()["code"]) == (409, "self_removal")
    assert "propre accès" in r.json()["message"]
    assert store.roles[ADMIN]["role"] == "admin"


def test_remove(client: TestClient) -> None:
    r = call(client, "DELETE", f"/roles/{COACH}")
    assert r.json() == {"status": "success"}
    # Applied at once on this instance: the next request of the removed coach is refused
    assert client.get("/api/email-status", headers={"Authorization": f"Bearer {COACH}"}).status_code == 403


def test_history(client: TestClient, clock: FakeClock) -> None:
    call(client, "POST", "/roles", email=STRANGER, role="readonly")
    clock.advance(minutes=1)
    call(client, "PATCH", f"/roles/{STRANGER}", role="coach")
    history = call(client, "GET", "/history").json()
    assert [(h["action"], h["author"], h["old_role"], h["new_role"]) for h in history] == [
        ("role_changed", ADMIN, "readonly", "coach"), ("invited", ADMIN, None, "readonly")]


def test_me_records_the_sign_in_date(client: TestClient, store: InMemoryAccessStore) -> None:
    client.get("/api/me", headers={"Authorization": f"Bearer {COACH}"})
    assert store.roles[COACH]["last_sign_in_at"] == "2026-10-30T09:00:00+00:00"


def test_me_of_a_stranger_writes_nothing(client: TestClient, store: InMemoryAccessStore) -> None:
    assert me(client, STRANGER) == {"email": STRANGER, "role": None, "invitation_expired_at": None}
    assert store.writes == 3  # the fixture's entries only


def test_me_passes_on_503(client: TestClient, store: InMemoryAccessStore) -> None:
    store.failing = True
    r = client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"})
    assert (r.status_code, r.json()["code"]) == (503, "access_unavailable")


def test_me_answers_when_the_acceptance_fails(client: TestClient, store: InMemoryAccessStore) -> None:
    call(client, "POST", "/roles", email="neville@alj.example", role="coach")
    with patch.object(store, "update_role", side_effect=RuntimeError("quota")):
        assert me(client, "neville@alj.example")["role"] == "coach"
    assert store.roles["neville@alj.example"]["invitation_expires_at"] is not None
    me(client, "neville@alj.example")  # tried again on the next page load
    assert store.roles["neville@alj.example"]["invitation_expires_at"] is None
