"""Access rules: invitations and changes to the access list, their safeguards and history, and sign-ins."""

from __future__ import annotations

from unittest.mock import patch

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


# ---------------------------------------------------------------- Invitations
def test_invite_normalises_and_records(rules: AccessRules, store: InMemoryAccessStore) -> None:
    entry = rules.invite(ADMIN, "  Neville@ALJ.example ", "coach", "  Neville   L. ")
    assert entry["email"] == "neville@alj.example"
    assert store.roles["neville@alj.example"] == entry
    assert (entry["role"], entry["display_name"], entry["created_by"]) == ("coach", "Neville L.", ADMIN)
    assert (entry["invited_at"], entry["invitation_expires_at"]) == ("2026-10-30T09:00:00+00:00", "2026-11-06T09:00:00+00:00")
    assert entry["invitation_sent_at"] is None and entry["accepted_at"] is None
    assert actions(store) == [("invited", "neville@alj.example", None, "coach")]
    assert store.history[0]["author"] == ADMIN
    assert store.history[0]["at"] == "2026-10-30T09:00:00+00:00"


@pytest.mark.parametrize("email", ["", "pas-une-adresse", "a@b"])
def test_invite_refuses_an_invalid_address(rules: AccessRules, store: InMemoryAccessStore, email: str) -> None:
    with pytest.raises(InvalidRequest):
        rules.invite(ADMIN, email, "coach")
    assert store.history == []


def test_invite_refuses_an_unknown_role(rules: AccessRules) -> None:
    with pytest.raises(InvalidRequest):
        rules.invite(ADMIN, STRANGER, "owner")


def test_invite_refuses_a_listed_address(rules: AccessRules, store: InMemoryAccessStore) -> None:
    with pytest.raises(Conflict, match="déjà un accès") as refused:
        rules.invite(ADMIN, " SEVERUS@alj.example", "admin")
    assert refused.value.code == "already_listed"
    assert store.roles[COACH]["role"] == "coach"
    assert store.history == []


def test_invite_twice_points_to_resend(rules: AccessRules) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    with pytest.raises(Conflict, match="Renvoyer") as refused:
        rules.invite(ADMIN, STRANGER, "admin")
    assert refused.value.code == "already_invited"


def test_pending_invitation_gives_the_role_until_it_expires(rules: AccessRules, directory: RoleDirectory, clock: FakeClock) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    clock.advance(days=7, seconds=-1)
    assert directory.role_of(STRANGER) == Role.COACH
    assert directory.expired_invitation_of(STRANGER) is None
    clock.advance(seconds=1)
    assert directory.role_of(STRANGER) is None
    assert directory.expired_invitation_of(STRANGER) == "2026-11-06T09:00:00+00:00"


def test_entries_without_invitation_never_expire(directory: RoleDirectory, clock: FakeClock) -> None:
    clock.advance(days=365)
    assert directory.role_of(COACH) == Role.COACH
    assert directory.expired_invitation_of(COACH) is None
    assert directory.expired_invitation_of(STRANGER) is None


def test_unreadable_expiry_counts_as_expired(store: InMemoryAccessStore, directory: RoleDirectory) -> None:
    store.save_role(role_entry(STRANGER, "coach", invitation_expires_at="bientôt"))
    assert directory.role_of(STRANGER) is None


def test_bootstrap_address_stays_admin_with_an_expired_invitation(store: InMemoryAccessStore, clock: FakeClock) -> None:
    store.save_role(role_entry(STRANGER, "readonly", invitation_expires_at="2026-10-01T09:00:00+00:00"))
    assert RoleDirectory(store, clock, bootstrap_email=STRANGER).role_of(STRANGER) == Role.ADMIN


def test_accept_invitation(rules: AccessRules, directory: RoleDirectory, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    clock.advance(days=3)
    rules.accept_invitation(" Draco@ALJ.example")
    assert store.roles[STRANGER]["invitation_expires_at"] is None
    assert store.roles[STRANGER]["accepted_at"] == "2026-11-02T09:00:00+00:00"
    clock.advance(days=30)
    assert directory.role_of(STRANGER) == Role.COACH
    writes = store.writes
    rules.accept_invitation(STRANGER)  # already accepted: nothing written
    assert store.writes == writes


def test_accept_is_tried_again_after_a_failed_write(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    with patch.object(store, "update_role", side_effect=RuntimeError("quota")), pytest.raises(RuntimeError):
        rules.accept_invitation(STRANGER)
    rules.accept_invitation(STRANGER)  # same day, same instance: not remembered as done
    assert store.roles[STRANGER]["invitation_expires_at"] is None


def test_accept_skips_an_entry_removed_meanwhile(rules: AccessRules, directory: RoleDirectory, store: InMemoryAccessStore) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    directory.entries()  # cached with the invitation
    del store.roles[STRANGER]  # removed on another instance
    rules.accept_invitation(STRANGER)
    assert STRANGER not in store.roles


def test_accept_ignores_entries_without_invitation(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.accept_invitation(COACH)
    rules.accept_invitation(STRANGER)
    assert store.writes == 0


def test_renew_invitation(rules: AccessRules, directory: RoleDirectory, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    rules.mark_invitation_sent(STRANGER)
    clock.advance(days=10)
    assert directory.role_of(STRANGER) is None
    entry = rules.renew_invitation(OTHER_ADMIN, STRANGER)
    assert (entry["invited_at"], entry["invitation_expires_at"]) == ("2026-11-09T09:00:00+00:00", "2026-11-16T09:00:00+00:00")
    assert entry["invitation_sent_at"] is None
    assert store.roles[STRANGER] == entry
    assert directory.role_of(STRANGER) == Role.COACH
    assert actions(store)[-1] == ("invitation_resent", STRANGER, "coach", "coach")
    assert store.history[-1]["author"] == OTHER_ADMIN


def test_renew_refused_for_an_accepted_access(rules: AccessRules) -> None:
    with pytest.raises(Conflict) as refused:
        rules.renew_invitation(ADMIN, COACH)
    assert refused.value.code == "not_invited"
    with pytest.raises(NotFound):
        rules.renew_invitation(ADMIN, STRANGER)


def test_mark_invitation_sent(rules: AccessRules, store: InMemoryAccessStore, clock: FakeClock) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    clock.advance(seconds=2)
    assert rules.mark_invitation_sent(STRANGER)["invitation_sent_at"] == "2026-10-30T09:00:02+00:00"
    assert store.roles[STRANGER]["invitation_sent_at"] == "2026-10-30T09:00:02+00:00"
    assert len(store.history) == 1


def test_pending_invitation_can_be_changed_and_removed(rules: AccessRules, store: InMemoryAccessStore) -> None:
    rules.invite(ADMIN, STRANGER, "coach")
    assert rules.change_role(ADMIN, STRANGER, "readonly")["invitation_expires_at"] == "2026-11-06T09:00:00+00:00"
    rules.remove(ADMIN, STRANGER)
    assert STRANGER not in store.roles


# ---------------------------------------------------------------- Changes


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
    rules.invite(ADMIN, STRANGER, "readonly")
    clock.advance(minutes=1)
    rules.change_role(ADMIN, STRANGER, "coach")
    assert [h["action"] for h in rules.history()] == ["role_changed", "invited"]
    assert len(rules.history(limit=1)) == 1


def test_without_day_memory_the_store_is_read_again(store: InMemoryAccessStore, directory: RoleDirectory, clock: FakeClock) -> None:
    """Dev mode: the emulator re-seeded under a running server loses the sign-in date; the next sign-in writes it again."""
    rules = AccessRules(store, directory, clock, remember_days=False)
    rules.record_sign_in(COACH)
    store.save_role(role_entry(COACH, "coach"))  # re-seed
    directory.invalidate()
    rules.record_sign_in(COACH)
    assert store.roles[COACH]["last_sign_in_at"] == "2026-10-30T09:00:00+00:00"


def test_server_rules_forget_the_days_in_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.security import role_directory
    from services.access import rules as access_rules
    from support.fake_access import install_access

    for env, remember in (("dev", False), ("prod", True)):
        monkeypatch.setenv("ALJ_ENV", env)
        install_access()
        assert access_rules.current()._remember_days is remember
    role_directory.install(None)
