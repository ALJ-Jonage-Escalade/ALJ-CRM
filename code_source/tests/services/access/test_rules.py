"""Access rules: changes to the access list, their safeguards and history, the access requests and sign-in dates."""

from __future__ import annotations

import pytest

from infrastructure.security.role_directory import RoleDirectory
from infrastructure.security.roles import Role
from services.access.rules import AccessRules
from services.errors import Conflict, InvalidRequest, NotFound
from support.fake_access import FakeClock, InMemoryAccessStore, role_entry

ADMIN = "albus@alj.example"
OTHER_ADMIN = "minerva@alj.example"
COACH = "severus@alj.example"
STRANGER = "draco@alj.example"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> InMemoryAccessStore:
    store = InMemoryAccessStore()
    store.save_role(role_entry(ADMIN, "admin", "Albus"))
    store.save_role(role_entry(COACH, "coach", "Severus"))
    store.writes = 0
    return store


@pytest.fixture
def directory(store: InMemoryAccessStore, clock: FakeClock) -> RoleDirectory:
    return RoleDirectory(store, clock)


@pytest.fixture
def rules(store: InMemoryAccessStore, directory: RoleDirectory, clock: FakeClock) -> AccessRules:
    return AccessRules(store, directory, clock)


def actions(store: InMemoryAccessStore) -> list[tuple[str, str, str | None, str | None]]:
    return [(h["action"], h["target_email"], h["old_role"], h["new_role"]) for h in store.history]


# ---------------------------------------------------------------- Changes
def test_grant_normalises_and_records(rules: AccessRules, store: InMemoryAccessStore) -> None:
    entry = rules.grant(ADMIN, "  Neville@ALJ.example ", "coach", "  Neville   L. ")
    assert entry["email"] == "neville@alj.example"
    assert store.roles["neville@alj.example"]["role"] == "coach"
    assert store.roles["neville@alj.example"]["display_name"] == "Neville L."
    assert store.roles["neville@alj.example"]["created_by"] == ADMIN
    assert actions(store) == [("added", "neville@alj.example", None, "coach")]
    assert store.history[0]["author"] == ADMIN
    assert store.history[0]["at"] == "2026-10-30T09:00:00+00:00"


@pytest.mark.parametrize("email", ["", "pas-une-adresse", "a@b"])
def test_grant_refuses_an_invalid_address(rules: AccessRules, store: InMemoryAccessStore, email: str) -> None:
    with pytest.raises(InvalidRequest):
        rules.grant(ADMIN, email, "coach")
    assert store.history == []


def test_grant_refuses_an_unknown_role(rules: AccessRules) -> None:
    with pytest.raises(InvalidRequest):
        rules.grant(ADMIN, STRANGER, "owner")


def test_grant_refuses_a_listed_address(rules: AccessRules, store: InMemoryAccessStore) -> None:
    with pytest.raises(Conflict, match="déjà un accès"):
        rules.grant(ADMIN, " SEVERUS@alj.example", "admin")
    assert store.roles[COACH]["role"] == "coach"
    assert store.history == []


def test_change_role_applies_at_once(rules: AccessRules, directory: RoleDirectory, store: InMemoryAccessStore) -> None:
    assert directory.role_of(COACH) == Role.COACH
    entry = rules.change_role(ADMIN, COACH, "admin")
    assert entry["role"] == "admin"
    assert entry["updated_by"] == ADMIN
    assert directory.role_of(COACH) == Role.ADMIN  # cache dropped on this instance
    assert actions(store) == [("role_changed", COACH, "coach", "admin")]


def test_same_role_writes_nothing(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.change_role(ADMIN, COACH, "coach")
    assert store.writes == 0


def test_rename(rules: AccessRules, store: InMemoryAccessStore) -> None:
    assert rules.rename(ADMIN, COACH, "Prof. Rogue")["display_name"] == "Prof. Rogue"
    assert actions(store) == [("name_changed", COACH, "coach", "coach")]


def test_remove(rules: AccessRules, directory: RoleDirectory, store: InMemoryAccessStore) -> None:
    assert directory.role_of(COACH) == Role.COACH
    rules.remove(ADMIN, COACH)
    assert COACH not in store.roles
    assert directory.role_of(COACH) is None
    assert actions(store) == [("removed", COACH, "coach", None)]


def test_unknown_entry(rules: AccessRules) -> None:
    for change in (lambda: rules.remove(ADMIN, STRANGER), lambda: rules.change_role(ADMIN, STRANGER, "coach"),
                   lambda: rules.rename(ADMIN, STRANGER, "x")):
        with pytest.raises(NotFound):
            change()


# ---------------------------------------------------------------- Safeguards
def test_no_self_removal(rules: AccessRules, store: InMemoryAccessStore) -> None:
    store.save_role(role_entry(OTHER_ADMIN, "admin"))
    with pytest.raises(Conflict, match="propre accès"):
        rules.remove(" Albus@ALJ.example", ADMIN)
    assert ADMIN in store.roles


def test_no_self_demotion(rules: AccessRules, store: InMemoryAccessStore) -> None:
    store.save_role(role_entry(OTHER_ADMIN, "admin"))
    with pytest.raises(Conflict, match="propre rôle"):
        rules.change_role(ADMIN, ADMIN, "coach")
    assert store.roles[ADMIN]["role"] == "admin"


def test_last_admin_kept(rules: AccessRules, store: InMemoryAccessStore) -> None:
    """Another admin (not listed, e.g. the bootstrap one or the local server) can't remove the last listed admin."""
    with pytest.raises(Conflict, match="dernier administrateur"):
        rules.remove(OTHER_ADMIN, ADMIN)
    with pytest.raises(Conflict, match="dernier administrateur"):
        rules.change_role(OTHER_ADMIN, ADMIN, "readonly")
    assert store.roles[ADMIN]["role"] == "admin"
    assert store.history == []


def test_an_admin_among_several_can_go(rules: AccessRules, store: InMemoryAccessStore) -> None:
    store.save_role(role_entry(OTHER_ADMIN, "admin"))
    rules.change_role(ADMIN, OTHER_ADMIN, "coach")
    assert store.roles[OTHER_ADMIN]["role"] == "coach"


# ---------------------------------------------------------------- Access requests
def test_refused_sign_in_becomes_a_request(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.record_refused_sign_in(" Draco@ALJ.example", "Draco Malfoy")
    assert [r["email"] for r in rules.list_requests()] == [STRANGER]
    request = store.requests[STRANGER]
    assert request["google_display_name"] == "Draco Malfoy"
    assert request["first_requested_at"] == request["last_requested_at"] == "2026-10-30T09:00:00+00:00"


def test_repeated_sign_in_updates_the_same_request(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.record_refused_sign_in(STRANGER, "Draco")
    writes = store.writes
    rules.record_refused_sign_in(STRANGER, "Draco")  # same day: nothing written
    assert store.writes == writes
    clock.advance(days=2)
    rules.record_refused_sign_in(STRANGER, "Draco M.")
    assert len(store.requests) == 1
    assert store.requests[STRANGER]["first_requested_at"] == "2026-10-30T09:00:00+00:00"
    assert store.requests[STRANGER]["last_requested_at"] == "2026-11-01T09:00:00+00:00"
    assert store.requests[STRANGER]["google_display_name"] == "Draco M."


def test_grant_request(rules: AccessRules, store: InMemoryAccessStore, directory: RoleDirectory) -> None:
    rules.record_refused_sign_in(STRANGER, "Draco Malfoy")
    entry = rules.grant_request(ADMIN, STRANGER, "coach")
    assert entry["display_name"] == "Draco Malfoy"
    assert directory.role_of(STRANGER) == Role.COACH
    assert rules.list_requests() == []
    assert actions(store) == [("request_granted", STRANGER, None, "coach")]


def test_grant_without_request(rules: AccessRules) -> None:
    with pytest.raises(NotFound):
        rules.grant_request(ADMIN, STRANGER, "coach")


def test_manual_grant_clears_the_request(rules: AccessRules) -> None:
    rules.record_refused_sign_in(STRANGER)
    rules.grant(ADMIN, STRANGER, "readonly")
    assert rules.list_requests() == []


def test_dismissed_address_ignored_for_30_days(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.record_refused_sign_in(STRANGER)
    rules.dismiss_request(ADMIN, STRANGER)
    assert rules.list_requests() == []
    assert actions(store) == [("request_dismissed", STRANGER, None, None)]
    clock.advance(days=29)
    rules.record_refused_sign_in(STRANGER)
    assert rules.list_requests() == []
    clock.advance(days=1)
    rules.record_refused_sign_in(STRANGER)
    assert [r["email"] for r in rules.list_requests()] == [STRANGER]
    assert store.requests[STRANGER]["first_requested_at"] == "2026-11-29T09:00:00+00:00"


def test_requests_older_than_30_days_dropped(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.record_refused_sign_in(STRANGER)
    clock.advance(days=10)
    rules.record_refused_sign_in("neville@alj.example")
    clock.advance(days=20)
    assert [r["email"] for r in rules.list_requests()] == ["neville@alj.example"]
    assert STRANGER not in store.requests  # deleted on read


def test_requests_latest_first(rules: AccessRules, clock: FakeClock) -> None:
    rules.record_refused_sign_in(STRANGER)
    clock.advance(hours=1)
    rules.record_refused_sign_in("neville@alj.example")
    assert [r["email"] for r in rules.list_requests()] == ["neville@alj.example", STRANGER]


def test_invalid_address_never_recorded(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.record_refused_sign_in("not an address")
    assert store.requests == {}


# ---------------------------------------------------------------- Sign-in dates
def test_last_sign_in_written_once_a_day(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.record_sign_in(COACH)
    assert store.roles[COACH]["last_sign_in_at"] == "2026-10-30T09:00:00+00:00"
    writes = store.writes
    clock.advance(hours=5)
    rules.record_sign_in(COACH)
    assert store.writes == writes
    clock.advance(days=1)
    rules.record_sign_in(COACH)
    assert store.roles[COACH]["last_sign_in_at"] == "2026-10-31T14:00:00+00:00"
    assert store.history == []  # not an access change


def test_sign_in_already_recorded_today_by_another_instance(rules: AccessRules, store: InMemoryAccessStore) -> None:
    store.update_role(COACH, {"last_sign_in_at": "2026-10-30T07:00:00+00:00"})
    writes = store.writes
    rules.record_sign_in(COACH)
    assert store.writes == writes


def test_sign_in_of_an_unlisted_address(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.record_sign_in(STRANGER)
    assert STRANGER not in store.roles


# ---------------------------------------------------------------- History
def test_history_latest_first(rules: AccessRules, clock: FakeClock) -> None:
    rules.grant(ADMIN, STRANGER, "readonly")
    clock.advance(minutes=1)
    rules.change_role(ADMIN, STRANGER, "coach")
    assert [h["action"] for h in rules.history()] == ["role_changed", "added"]
    assert len(rules.history(limit=1)) == 1


def test_without_day_memory_the_store_is_read_again(store: InMemoryAccessStore, directory: RoleDirectory, clock: FakeClock) -> None:
    """Dev mode: the emulator re-seeded under a running server loses the request; the next sign-in records it again."""
    rules = AccessRules(store, directory, clock, remember_days=False)
    rules.record_refused_sign_in(STRANGER)
    store.requests.clear()  # re-seed
    rules.record_refused_sign_in(STRANGER)
    assert STRANGER in store.requests


def test_server_rules_forget_the_days_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.security import role_directory
    from services.access import rules as access_rules
    from support.fake_access import install_access

    for env, remember in (("dev", False), ("prod", True)):
        monkeypatch.setenv("ALJ_ENV", env)
        install_access()
        assert access_rules.current()._remember_days is remember
    role_directory.install(None)
