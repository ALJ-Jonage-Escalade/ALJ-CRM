"""SecretStore on Cloud Run: the Google OAuth values come from and go to Firestore (server_credentials/google_oauth),
a failed read is retried later, and a failed write is reported without changing anything."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from infrastructure.firestore.client import FirestoreClient, FirestoreError
from infrastructure.security import secret_store
from infrastructure.security.secret_store import SecretPersistenceError, SecretStore

DOC = {"refresh_token": "fs-refresh", "user_email": "club@alj.example", "client_id": "fs-cid", "client_secret": "fs-sec",
       "_doc_id": "google_oauth"}
KEYS = ("GMAIL_REFRESH_TOKEN", "GMAIL_USER_EMAIL", "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET")


@pytest.fixture
def cloud_run(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Cloud Run environment with env values that Firestore must override, and a fresh module cache."""
    monkeypatch.setenv("K_SERVICE", "alj-escalade-api")
    for key in KEYS:
        monkeypatch.setenv(key, f"env-{key}")
    monkeypatch.setattr(secret_store, "_firestore_values", {})
    monkeypatch.setattr(secret_store, "_firestore_loaded", False)
    monkeypatch.setattr(secret_store, "_last_failed_load", -secret_store.RELOAD_AFTER_FAILURE)
    yield


def test_get_secret_reads_all_oauth_values_from_firestore(cloud_run: None) -> None:
    with patch.object(FirestoreClient, "get_document", return_value=dict(DOC)) as get_document:
        values = {key: SecretStore.get_secret(key) for key in KEYS}
    assert values == {"GMAIL_REFRESH_TOKEN": "fs-refresh", "GMAIL_USER_EMAIL": "club@alj.example",
                      "GMAIL_CLIENT_ID": "fs-cid", "GMAIL_CLIENT_SECRET": "fs-sec"}
    get_document.assert_called_once_with("server_credentials", "google_oauth")


def test_failed_firestore_read_falls_back_to_env_then_retries(cloud_run: None) -> None:
    clock = [1000.0]
    with patch.object(secret_store.time, "monotonic", side_effect=lambda: clock[0]), \
         patch.object(FirestoreClient, "get_document", side_effect=FirestoreError("HTTP 503")) as get_document:
        assert SecretStore.get_secret("GMAIL_REFRESH_TOKEN") == "env-GMAIL_REFRESH_TOKEN"
        assert SecretStore.get_secret("GMAIL_REFRESH_TOKEN") == "env-GMAIL_REFRESH_TOKEN"
        assert get_document.call_count == 1  # not hammered on every call
        clock[0] += secret_store.RELOAD_AFTER_FAILURE
        get_document.side_effect = None
        get_document.return_value = dict(DOC)
        assert SecretStore.get_secret("GMAIL_REFRESH_TOKEN") == "fs-refresh"  # recovered without a restart
        assert get_document.call_count == 2


def test_set_secrets_writes_firestore_in_one_update(cloud_run: None) -> None:
    with patch.object(FirestoreClient, "get_document", return_value={}), \
         patch.object(FirestoreClient, "update_fields") as update_fields:
        SecretStore.set_secrets({"GMAIL_REFRESH_TOKEN": "new-refresh", "GMAIL_CLIENT_ID": "new-cid"})
        assert SecretStore.get_secret("GMAIL_REFRESH_TOKEN") == "new-refresh"
    update_fields.assert_called_once()
    collection, document, patch_fields = update_fields.call_args.args
    assert (collection, document) == ("server_credentials", "google_oauth")
    assert patch_fields["refresh_token"] == "new-refresh" and patch_fields["client_id"] == "new-cid"
    assert os.environ["GMAIL_CLIENT_ID"] == "new-cid"


def test_failed_firestore_write_raises_and_changes_nothing(cloud_run: None) -> None:
    with patch.object(FirestoreClient, "get_document", return_value=dict(DOC)), \
         patch.object(FirestoreClient, "update_fields", side_effect=FirestoreError("HTTP 503")):
        with pytest.raises(SecretPersistenceError) as raised:
            SecretStore.set_secret("GMAIL_REFRESH_TOKEN", "never-saved")
        assert SecretStore.get_secret("GMAIL_REFRESH_TOKEN") == "fs-refresh"
    assert os.environ["GMAIL_REFRESH_TOKEN"] == "env-GMAIL_REFRESH_TOKEN"
    assert "never-saved" not in str(raised.value)  # the message names the key, never the value


def test_local_set_secret_writes_the_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("K_CONFIGURATION", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nOTHER=1\nALJ_TEST_KEY=old\n", encoding="utf-8")
    monkeypatch.setattr(secret_store, "_env_file_path", lambda: str(env_file))
    monkeypatch.delenv("ALJ_TEST_KEY", raising=False)
    SecretStore.set_secret("ALJ_TEST_KEY", "new")
    assert env_file.read_text(encoding="utf-8") == "# comment\nOTHER=1\nALJ_TEST_KEY=new\n"
    assert SecretStore.get_secret("ALJ_TEST_KEY") == "new"
