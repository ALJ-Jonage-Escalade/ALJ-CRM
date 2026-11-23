"""Configuration pytest commune : sortie console en UTF-8 (émojis des modules applicatifs)."""
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import pytest

# Shared test helpers (tests/support/): importable by every test module, which pytest
# imports in importlib mode (no automatic sys.path entry for the tests folders).
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SRC_DIR = os.path.join(os.path.dirname(_TESTS_DIR), "src")
for _path in (_SRC_DIR, _TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Dev mode variables (dev/dev.env): removed so the tests stay in production mode
# even if the developer loaded them into their shell.
_DEV_ENV_KEYS = ("ALJ_ENV", "FIRESTORE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST",
                 "ALJ_DATA_DIR",
                 "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM_EMAIL", "SMTP_SENDER_ALIASES",
                 "GMAIL_USER_EMAIL", "GMAIL_CLIENT_ID", "GMAIL_REFRESH_TOKEN")


@pytest.fixture(autouse=True)
def _production_environment(monkeypatch):
    for key in _DEV_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    # The SQLite cache stays local: a test that needs Firestore replication turns it on itself
    monkeypatch.setenv("ALJ_CACHE_REPLICATION", "off")


@pytest.fixture(autouse=True)
def _frontend_build(monkeypatch, tmp_path_factory):
    """A stub build of the Vue app (frontend/dist): the pages it serves answer 200 whether `npm run build` ran or not
    (the CI's Python job does not build it). TestVueApp sets its own folder."""
    dist = tmp_path_factory.getbasetemp() / "frontend-dist"
    if not dist.exists():
        dist.mkdir()
        (dist / "index.html").write_text('<div id="app"></div>', encoding="utf-8")
    monkeypatch.setenv("ALJ_FRONTEND_DIST", str(dist))


@pytest.fixture(autouse=True)
def _test_client_host(monkeypatch):
    """Starlette's TestClient sends `Host: testserver`: accepted by the local-server guard in tests only."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from infrastructure.security import api_auth
    monkeypatch.setattr(api_auth, "LOCAL_HOSTS", api_auth.LOCAL_HOSTS | {"testserver"})


@pytest.fixture(autouse=True)
def _in_memory_access_list():
    """The access list (Firestore access_roles…) in memory and empty: no test reads the real one, and an address only
    has a role once a test lists it (support/fake_access.grant_roles)."""
    from support.fake_access import install_access
    from infrastructure.security import role_directory
    install_access()
    yield
    role_directory.install(None)


@pytest.fixture(autouse=True)
def email_log_store():
    """The e-mail log in memory and empty: every sender records its sends here, never in the real Firestore."""
    from support.fake_email_log import InMemoryEmailLogStore
    from services.communications import email_log
    store = InMemoryEmailLogStore()
    email_log.install(store)
    yield store
    email_log.install(None)


@pytest.fixture(autouse=True)
def _fresh_allowed_senders():
    """The allowed senders are read again by every test (they follow its environment variables)."""
    from services.communications.senders import forget_allowed_senders
    forget_allowed_senders()
    yield
    forget_allowed_senders()
