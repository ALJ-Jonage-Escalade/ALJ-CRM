"""Role directory: the role of an address from the access list, its one-minute cache and the bootstrap admin."""

from __future__ import annotations

import pytest

from infrastructure.security.role_directory import AccessUnavailable, RoleDirectory
from infrastructure.security.roles import Role
from support.fake_access import FakeClock, InMemoryAccessStore, role_entry

BOOT = "boot@alj-escalade.fr"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> InMemoryAccessStore:
    store = InMemoryAccessStore()
    for email, role in (("admin@alj.example", "admin"), ("coach@alj.example", "coach"), ("ro@alj.example", "readonly")):
        store.save_role(role_entry(email, role))
    return store


def test_role_of_listed_and_unknown_addresses(store: InMemoryAccessStore, clock: FakeClock) -> None:
    directory = RoleDirectory(store, clock)
    assert directory.role_of("admin@alj.example") == Role.ADMIN
    assert directory.role_of("coach@alj.example") == Role.COACH
    assert directory.role_of("ro@alj.example") == Role.READONLY
    assert directory.role_of("stranger@alj.example") is None
    assert directory.role_of("") is None


def test_role_of_ignores_case_and_whitespace(store: InMemoryAccessStore, clock: FakeClock) -> None:
    assert RoleDirectory(store, clock).role_of("  Coach@ALJ.example ") == Role.COACH


def test_unknown_role_value_gives_no_access(store: InMemoryAccessStore, clock: FakeClock) -> None:
    store.save_role(role_entry("odd@alj.example", "superuser"))
    assert RoleDirectory(store, clock).role_of("odd@alj.example") is None


def test_cache_served_within_a_minute_then_reloaded(store: InMemoryAccessStore, clock: FakeClock) -> None:
    directory = RoleDirectory(store, clock)
    assert directory.role_of("coach@alj.example") == Role.COACH
    store.save_role(role_entry("coach@alj.example", "admin"))
    clock.advance(seconds=59)
    assert directory.role_of("coach@alj.example") == Role.COACH
    assert store.role_reads == 1
    clock.advance(seconds=1)
    assert directory.role_of("coach@alj.example") == Role.ADMIN
    assert store.role_reads == 2


def test_invalidate_applies_at_once(store: InMemoryAccessStore, clock: FakeClock) -> None:
    directory = RoleDirectory(store, clock)
    assert directory.role_of("coach@alj.example") == Role.COACH
    store.delete_role("coach@alj.example")
    directory.invalidate()
    assert directory.role_of("coach@alj.example") is None


def test_bootstrap_admin_with_an_empty_list(clock: FakeClock) -> None:
    directory = RoleDirectory(InMemoryAccessStore(), clock, bootstrap_email=" Boot@ALJ-Escalade.fr ")
    assert directory.role_of(BOOT) == Role.ADMIN
    assert directory.role_of("other@alj.example") is None


def test_bootstrap_admin_when_the_store_is_unreadable(store: InMemoryAccessStore, clock: FakeClock) -> None:
    store.failing = True
    directory = RoleDirectory(store, clock, bootstrap_email=BOOT)
    assert directory.role_of(BOOT) == Role.ADMIN
    with pytest.raises(AccessUnavailable):
        directory.role_of("coach@alj.example")


def test_listed_bootstrap_address_gets_its_listed_role(store: InMemoryAccessStore, clock: FakeClock) -> None:
    """A role changed on the page sticks; the emergency access only applies while unlisted or unreadable."""
    store.save_role(role_entry(BOOT, "coach"))
    directory = RoleDirectory(store, clock, bootstrap_email=BOOT)
    assert directory.role_of(BOOT) == Role.COACH


def test_unavailable_once_the_cache_has_expired(store: InMemoryAccessStore, clock: FakeClock) -> None:
    directory = RoleDirectory(store, clock)
    assert directory.role_of("coach@alj.example") == Role.COACH
    store.failing = True
    assert directory.role_of("coach@alj.example") == Role.COACH  # still cached
    clock.advance(seconds=60)
    with pytest.raises(AccessUnavailable):
        directory.role_of("coach@alj.example")
    store.failing = False
    assert directory.role_of("coach@alj.example") == Role.COACH  # back once readable


def test_no_cache_reads_every_time(store: InMemoryAccessStore, clock: FakeClock) -> None:
    """Dev mode (cache_seconds=0): a re-seed of the emulator under a running server applies at once."""
    directory = RoleDirectory(store, clock, cache_seconds=0)
    assert directory.role_of("stranger@alj.example") is None
    store.save_role(role_entry("stranger@alj.example", "admin"))
    assert directory.role_of("stranger@alj.example") == Role.ADMIN


def test_server_directory_has_no_cache_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.security import role_directory

    for env, cache in (("dev", 0), ("prod", role_directory.CACHE_SECONDS)):
        monkeypatch.setenv("ALJ_ENV", env)
        role_directory.install(None)
        assert role_directory.current()._cache_seconds == cache
    role_directory.install(None)
