"""Routes of Administration › Accès (/api/admin/access) and the sign-ins /api/me records, token checks on."""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

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
def client(store: InMemoryAccessStore, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    install_access(store, clock)
    monkeypatch.setenv("ALJ_API_AUTH", "required")
    # The token's claims: the e-mail is the bearer token itself (signatures are tested in test_api_security)
    with patch("infrastructure.security.api_auth.verify_firebase_token",
               side_effect=lambda token: {"sub": token, "email": token, "email_verified": True, "name": "Google Name"}):
        yield TestClient(app)


def call(client: TestClient, method: str, path: str, who: str = ADMIN, **body: Any) -> Any:  # Any: JSON bodies
    return client.request(method, BASE + path, headers={"Authorization": f"Bearer {who}"}, json=body or None)


ROUTES = [("GET", "/roles"), ("POST", "/roles"), ("PATCH", f"/roles/{COACH}"), ("DELETE", f"/roles/{COACH}"),
          ("GET", "/requests"), ("POST", f"/requests/{STRANGER}/grant"), ("DELETE", f"/requests/{STRANGER}"),
          ("GET", "/history")]


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
                                "updated_at", "updated_by"}


def test_add_then_the_person_signs_in(client: TestClient) -> None:
    r = call(client, "POST", "/roles", email=" Neville@ALJ.example ", role="coach", display_name="Neville")
    assert r.status_code == 201
    assert (r.json()["email"], r.json()["role"], r.json()["created_by"]) == ("neville@alj.example", "coach", ADMIN)
    assert client.get("/api/me", headers={"Authorization": "Bearer neville@alj.example"}).json()["role"] == "coach"


def test_add_refusals(client: TestClient) -> None:
    r = call(client, "POST", "/roles", email="pas-une-adresse", role="coach")
    assert r.status_code == 400
    assert "invalide" in r.json()["message"]
    r = call(client, "POST", "/roles", email=COACH.upper(), role="admin")
    assert (r.status_code, r.json()["code"]) == (409, "already_listed")
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


def test_request_from_a_refused_sign_in_then_granted(client: TestClient, store: InMemoryAccessStore) -> None:
    me = client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"})
    assert me.json() == {"email": STRANGER, "role": None}
    requests = call(client, "GET", "/requests").json()
    assert requests == [{"email": STRANGER, "google_display_name": "Google Name",
                         "first_requested_at": "2026-10-30T09:00:00+00:00", "last_requested_at": "2026-10-30T09:00:00+00:00"}]
    r = call(client, "POST", f"/requests/{STRANGER}/grant", role="coach")
    assert r.status_code == 201
    assert (r.json()["role"], r.json()["display_name"]) == ("coach", "Google Name")
    assert call(client, "GET", "/requests").json() == []
    assert client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"}).json()["role"] == "coach"
    assert call(client, "POST", f"/requests/{STRANGER}/grant", role="coach").status_code == 404


def test_dismiss_request(client: TestClient) -> None:
    client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"})
    assert call(client, "DELETE", f"/requests/{STRANGER}").json() == {"status": "success"}
    assert call(client, "GET", "/requests").json() == []
    assert call(client, "DELETE", f"/requests/{STRANGER}").status_code == 404


def test_history(client: TestClient, clock: FakeClock) -> None:
    call(client, "POST", "/roles", email=STRANGER, role="readonly")
    clock.advance(minutes=1)
    call(client, "PATCH", f"/roles/{STRANGER}", role="coach")
    history = call(client, "GET", "/history").json()
    assert [(h["action"], h["author"], h["old_role"], h["new_role"]) for h in history] == [
        ("role_changed", ADMIN, "readonly", "coach"), ("added", ADMIN, None, "readonly")]


def test_me_records_the_sign_in_date(client: TestClient, store: InMemoryAccessStore) -> None:
    client.get("/api/me", headers={"Authorization": f"Bearer {COACH}"})
    assert store.roles[COACH]["last_sign_in_at"] == "2026-10-30T09:00:00+00:00"
    assert store.requests == {}


def test_me_passes_on_503_and_records_nothing(client: TestClient, store: InMemoryAccessStore) -> None:
    store.failing = True
    r = client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"})
    assert (r.status_code, r.json()["code"]) == (503, "access_unavailable")
    store.failing = False
    assert store.requests == {}


def test_me_answers_when_the_record_fails(client: TestClient, store: InMemoryAccessStore) -> None:
    with patch.object(store, "save_request", side_effect=RuntimeError("quota")):
        r = client.get("/api/me", headers={"Authorization": f"Bearer {STRANGER}"})
    assert r.json() == {"email": STRANGER, "role": None}
