"""RestStore.commit (cloud cache replication): Firestore's HTTP answers mapped to the errors flush relies on."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infrastructure.firestore.client import FirestoreConflictError, FirestoreError
from infrastructure.firestore.cloud_sync.rest_store import RestStore

WRITE = {"collection": "crm_users", "doc_id": "1", "fields": {"city": "Jonage"}, "mask": ["city"], "deleted": False,
         "by": "test", "precondition": {"exists": True}}


def _commit(status_code: int, text: str = "", payload: dict | None = None) -> list:
    response = MagicMock(status_code=status_code, text=text)
    response.json.return_value = payload or {}
    store = RestStore(project_id="demo-alj", token_provider=lambda: "token")
    with patch.object(RestStore, "_request", return_value=response) as request:
        result = store.commit([WRITE])
    body = request.call_args.kwargs["json"]["writes"][0]
    assert body["currentDocument"] == {"exists": True}
    assert body["updateMask"]["fieldPaths"][0] == "city"
    return result


def test_commit_returns_the_update_times() -> None:
    payload = {"writeResults": [{"updateTime": "2026-11-08T10:00:00Z",
                                 "transformResults": [{"timestampValue": "2026-11-08T10:00:01Z"}]}]}
    assert _commit(200, payload=payload) == [{"update_time": "2026-11-08T10:00:00Z", "modified_at": "2026-11-08T10:00:01Z"}]


@pytest.mark.parametrize(("status_code", "text"), [
    (404, "NOT_FOUND"),
    (409, "ABORTED"),
    (400, '{"error": {"status": "FAILED_PRECONDITION"}}'),
    (400, '{"error": {"status": "ALREADY_EXISTS"}}'),
])
def test_commit_conflicts_are_conflict_errors(status_code: int, text: str) -> None:
    with pytest.raises(FirestoreConflictError):
        _commit(status_code, text)


@pytest.mark.parametrize("status_code", [400, 403, 500, 503])
def test_commit_other_failures_are_sync_errors(status_code: int) -> None:
    with pytest.raises(FirestoreError) as raised:
        _commit(status_code, "INTERNAL")
    assert not isinstance(raised.value, FirestoreConflictError)
