"""Bootstrap admin: BOOTSTRAP_ADMIN_EMAIL joins the access list once, is never overwritten, skipped in dev mode."""

from __future__ import annotations

import logging

import pytest

from infrastructure.security.role_directory import RoleDirectory
from services.access.bootstrap import bootstrap_admin, run_at_startup
from support.fake_access import FakeClock, InMemoryAccessStore, role_entry

BOOT = "boot@alj-escalade.fr"


def test_creates_the_entry_once() -> None:
    store, clock = InMemoryAccessStore(), FakeClock()
    assert bootstrap_admin(store, clock, " Boot@ALJ-Escalade.fr ") is True
    assert store.roles[BOOT]["role"] == "admin"
    assert store.roles[BOOT]["created_by"] == "bootstrap"
    assert [(h["action"], h["author"], h["new_role"]) for h in store.history] == [("bootstrap", "bootstrap", "admin")]
    # Another instance starting at the same time: create-if-absent refuses, no second history entry
    assert bootstrap_admin(store, clock, BOOT) is False
    assert len(store.history) == 1


def test_never_overwrites_an_existing_entry() -> None:
    store = InMemoryAccessStore()
    store.save_role(role_entry(BOOT, "coach", "Changed on the page"))
    run_at_startup(RoleDirectory(store, FakeClock(), BOOT))
    assert store.roles[BOOT]["role"] == "coach"
    assert store.history == []


def test_run_at_startup_adds_and_invalidates() -> None:
    store = InMemoryAccessStore()
    directory = RoleDirectory(store, FakeClock(), BOOT)
    directory.entries()  # cached empty list
    run_at_startup(directory)
    assert BOOT in directory.entries()


def test_skipped_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALJ_ENV", "dev")
    store = InMemoryAccessStore()
    run_at_startup(RoleDirectory(store, FakeClock(), BOOT))
    assert store.roles == {}


def test_warns_without_setting(caplog: pytest.LogCaptureFixture) -> None:
    store = InMemoryAccessStore()
    with caplog.at_level(logging.WARNING, logger="alj"):
        run_at_startup(RoleDirectory(store, FakeClock(), ""))
    assert "BOOTSTRAP_ADMIN_EMAIL is not set" in caplog.text
    assert store.roles == {}


def test_invalid_setting_ignored(caplog: pytest.LogCaptureFixture) -> None:
    store = InMemoryAccessStore()
    with caplog.at_level(logging.WARNING, logger="alj"):
        run_at_startup(RoleDirectory(store, FakeClock(), "not-an-address"))
    assert "BOOTSTRAP_ADMIN_EMAIL ignored" in caplog.text
    assert store.roles == {}


def test_store_error_never_raises(caplog: pytest.LogCaptureFixture) -> None:
    store = InMemoryAccessStore()
    store.failing = True
    with caplog.at_level(logging.ERROR, logger="alj"):
        run_at_startup(RoleDirectory(store, FakeClock(), BOOT))
    assert "could not be updated" in caplog.text
