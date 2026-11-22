"""RestStore reads (cloud cache replication): pagination, batching, document parsing, HTTP and network failures."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from infrastructure.firestore.client import DEFAULT_PROJECT_ID, FirestoreError
from infrastructure.firestore.cloud_sync.rest_store import RestStore

ROOT = "projects/demo-alj/databases/(default)/documents"
REQUEST = "infrastructure.firestore.cloud_sync.rest_store.requests.request"


def _response(payload: object, status_code: int = 200) -> MagicMock:
    response = MagicMock(status_code=status_code, text="denied")
    response.json.return_value = payload
    return response


def _doc(doc_id: str, deleted: bool = False, modified_at: str | None = None, **fields: object) -> dict:
    raw = {name: {"integerValue": str(value)} if isinstance(value, int) else {"stringValue": value}
           for name, value in fields.items()}
    raw["_deleted"] = {"booleanValue": deleted}
    raw["_modified_by"] = {"stringValue": "poste"}
    if modified_at:
        raw["_modified_at"] = {"timestampValue": modified_at}
    return {"name": f"{ROOT}/crm_users/{doc_id}", "fields": raw, "updateTime": "2026-11-01T10:00:00Z"}


def _store() -> RestStore:
    return RestStore(project_id="demo-alj", token_provider=lambda: "token")


def test_list_all_follows_pages_and_parses_documents() -> None:
    pages = [_response({"documents": [_doc("1", city="Jonage")], "nextPageToken": "next"}),
             _response({"documents": [_doc("2", deleted=True, modified_at="2026-11-02T09:00:00Z")]})]
    with patch(REQUEST, side_effect=pages) as request:
        docs = _store().list_all("crm_users")
    assert docs == [
        {"id": "1", "fields": {"city": "Jonage"}, "deleted": False,
         "update_time": "2026-11-01T10:00:00Z", "modified_at": "2026-11-01T10:00:00Z"},
        {"id": "2", "fields": {}, "deleted": True,
         "update_time": "2026-11-01T10:00:00Z", "modified_at": "2026-11-02T09:00:00Z"},
    ]
    assert request.call_args_list[1].kwargs["params"] == {"pageSize": 300, "pageToken": "next"}
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer token"


def test_list_modified_since_skips_rows_without_document() -> None:
    with patch(REQUEST, return_value=_response([{"readTime": "x"}, {"document": _doc("1", city="Lyon")}])) as request:
        docs = _store().list_modified_since("crm_users", "2026-11-01T00:00:00Z")
    assert [doc["id"] for doc in docs] == ["1"]
    where = request.call_args.kwargs["json"]["structuredQuery"]["where"]["fieldFilter"]
    assert where["value"] == {"timestampValue": "2026-11-01T00:00:00Z"}


def test_get_many_batches_by_300_and_maps_missing_to_none() -> None:
    ids = [str(number) for number in range(301)] + ["0"]
    batches = [_response([{"found": _doc("0")}, {"missing": f"{ROOT}/crm_users/1"}]),
               _response([{"missing": f"{ROOT}/crm_users/300"}])]
    with patch(REQUEST, side_effect=batches) as request:
        result = _store().get_many("crm_users", ids)
    assert len(request.call_args_list[0].kwargs["json"]["documents"]) == 300
    assert request.call_args_list[1].kwargs["json"]["documents"] == [f"{ROOT}/crm_users/300"]
    assert result["0"]["id"] == "0"
    assert result["1"] is None and result["300"] is None


@pytest.mark.parametrize(("rows", "expected"), [
    pytest.param([{"document": _doc("7", id=42)}], 42, id="highest-id"),
    pytest.param([{"document": _doc("7", id="abc")}], 0, id="not-an-integer"),
    pytest.param([{"readTime": "x"}], 0, id="empty-collection"),
])
def test_max_int_id(rows: list, expected: int) -> None:
    with patch(REQUEST, return_value=_response(rows)):
        assert _store().max_int_id("crm_users", "id") == expected


@pytest.mark.parametrize("read", [
    lambda store: store.list_all("crm_users"),
    lambda store: store.list_modified_since("crm_users", "2026-11-01T00:00:00Z"),
    lambda store: store.get_many("crm_users", ["1"]),
    lambda store: store.max_int_id("crm_users", "id"),
], ids=["list_all", "list_modified_since", "get_many", "max_int_id"])
def test_read_http_failure_is_a_firestore_error(read) -> None:
    with patch(REQUEST, return_value=_response({}, status_code=403)), pytest.raises(FirestoreError, match="HTTP 403"):
        read(_store())


def test_network_failure_is_a_firestore_error() -> None:
    with patch(REQUEST, side_effect=requests.ConnectionError("down")), pytest.raises(FirestoreError, match="injoignable"):
        _store().list_all("crm_users")


def test_commit_without_writes_sends_nothing() -> None:
    with patch(REQUEST) as request:
        assert _store().commit([]) == []
    request.assert_not_called()


def test_token_comes_from_the_environment_before_google_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALJ_FIRESTORE_ACCESS_TOKEN", " env-token ")
    with patch(REQUEST, return_value=_response({})) as request:
        RestStore(project_id="demo-alj").list_all("crm_users")
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer env-token"


def test_project_id_falls_back_to_the_default_when_credentials_fail() -> None:
    with patch("infrastructure.firestore.cloud_sync.rest_store.FirestoreClient.get_project_id", side_effect=OSError("no ADC")):
        assert RestStore().project_id == DEFAULT_PROJECT_ID
