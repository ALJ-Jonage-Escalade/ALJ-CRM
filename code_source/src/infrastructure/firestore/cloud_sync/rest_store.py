"""Accès REST à Firestore pour le cache database.db."""
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

import requests

from infrastructure import runtime_env
from infrastructure.firestore.client import (
    DEFAULT_PROJECT_ID,
    FirestoreClient,
    FirestoreConflictError,
    FirestoreError,
    firestore_to_python_value,
    python_to_firestore_value,
)
from infrastructure.firestore.cloud_sync.common import BY_FIELD, DEL_FIELD, META_FIELDS, MOD_FIELD, quote_field_path


class RestStore:
    """Firestore operations of the cache replication (list, query, read, commit), on the project, token, value
    conversion and errors of FirestoreClient. Tests and scripts can give their own project and token."""

    def __init__(self, project_id: Optional[str] = None,
                 token_provider: Optional[Callable[[], str]] = None):
        self._project_id = project_id
        self._token_provider = token_provider

    @property
    def project_id(self) -> str:
        if not self._project_id:
            self._project_id = runtime_env.project_id_override()
        if not self._project_id:
            try:
                self._project_id = FirestoreClient.get_project_id()
            except Exception:
                self._project_id = DEFAULT_PROJECT_ID
        return self._project_id

    def _token(self) -> str:
        if self._token_provider:
            return self._token_provider()
        emulator_tok = runtime_env.emulator_token()
        if emulator_tok:
            return emulator_tok
        env_tok = os.environ.get("ALJ_FIRESTORE_ACCESS_TOKEN", "").strip()
        if env_tok:
            return env_tok
        return FirestoreClient.get_access_token()

    @property
    def _root(self) -> str:
        return f"projects/{self.project_id}/databases/(default)/documents"

    @property
    def _base(self) -> str:
        return f"{runtime_env.firestore_base_url()}/{self._root}"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kw) -> requests.Response:
        try:
            return requests.request(method, url, headers=self._headers(), timeout=60, **kw)
        except requests.RequestException as e:
            raise FirestoreError(f"Firestore injoignable : {e}")

    @staticmethod
    def _parse_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
        raw = doc.get("fields", {}) or {}
        fields = {k: firestore_to_python_value(v) for k, v in raw.items() if k not in META_FIELDS}
        return {
            "id": doc.get("name", "").rsplit("/", 1)[-1],
            "fields": fields,
            "deleted": bool(firestore_to_python_value(raw.get(DEL_FIELD, {"nullValue": None}))),
            "update_time": doc.get("updateTime"),
            "modified_at": firestore_to_python_value(raw.get(MOD_FIELD, {"nullValue": None})) or doc.get("updateTime"),
        }

    def list_all(self, collection: str) -> List[Dict[str, Any]]:
        url = f"{self._base}/{collection}"
        out: List[Dict[str, Any]] = []
        token: Optional[str] = None
        while True:
            params: Dict[str, Any] = {"pageSize": 300}  # Any: query values
            if token:
                params["pageToken"] = token
            resp = self._request("GET", url, params=params)
            if resp.status_code != 200:
                raise FirestoreError(f"Liste {collection} : HTTP {resp.status_code} - {resp.text[:200]}")
            payload = resp.json()
            out.extend(self._parse_doc(d) for d in payload.get("documents", []))
            token = payload.get("nextPageToken")
            if not token:
                return out

    def list_modified_since(self, collection: str, since: str) -> List[Dict[str, Any]]:
        url = f"{self._base}:runQuery"
        body = {"structuredQuery": {
            "from": [{"collectionId": collection}],
            "where": {"fieldFilter": {
                "field": {"fieldPath": MOD_FIELD},
                "op": "GREATER_THAN_OR_EQUAL",
                "value": {"timestampValue": since},
            }},
        }}
        resp = self._request("POST", url, json=body)
        if resp.status_code != 200:
            raise FirestoreError(f"Requête {collection} : HTTP {resp.status_code} - {resp.text[:200]}")
        return [self._parse_doc(r["document"]) for r in resp.json() if r.get("document")]

    def get_many(self, collection: str, doc_ids: Iterable[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        ids = list(dict.fromkeys(doc_ids))
        result: Dict[str, Optional[Dict[str, Any]]] = {}
        url = f"{self._base}:batchGet"
        for i in range(0, len(ids), 300):
            names = [f"{self._root}/{collection}/{d}" for d in ids[i:i + 300]]
            resp = self._request("POST", url, json={"documents": names})
            if resp.status_code != 200:
                raise FirestoreError(f"Lecture {collection} : HTTP {resp.status_code} - {resp.text[:200]}")
            for entry in resp.json():
                if entry.get("found"):
                    doc = self._parse_doc(entry["found"])
                    result[doc["id"]] = doc
                elif entry.get("missing"):
                    result[entry["missing"].rsplit("/", 1)[-1]] = None
        return result

    def max_int_id(self, collection: str, field: str) -> int:
        url = f"{self._base}:runQuery"
        body = {"structuredQuery": {
            "from": [{"collectionId": collection}],
            "orderBy": [{"field": {"fieldPath": quote_field_path(field)}, "direction": "DESCENDING"}],
            "limit": 1,
        }}
        resp = self._request("POST", url, json=body)
        if resp.status_code != 200:
            raise FirestoreError(f"Requête {collection} : HTTP {resp.status_code} - {resp.text[:200]}")
        for entry in resp.json():
            if entry.get("document"):
                value = self._parse_doc(entry["document"])["fields"].get(field)
                return int(value) if isinstance(value, int) else 0
        return 0

    def commit(self, writes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Écritures atomiques. Chaque écriture :
        {collection, doc_id, fields, mask (liste|None), deleted, by, precondition}
        Retourne [{update_time, modified_at}] dans l'ordre."""
        if not writes:
            return []
        url = f"{self._base}:commit"
        body = []
        for write in writes:
            fields = {k: python_to_firestore_value(v) for k, v in (write.get("fields") or {}).items()}
            fields[DEL_FIELD] = {"booleanValue": bool(write.get("deleted"))}
            fields[BY_FIELD] = {"stringValue": write.get("by") or ""}
            op: Dict[str, Any] = {
                "update": {"name": f"{self._root}/{write['collection']}/{write['doc_id']}", "fields": fields},
                "updateTransforms": [{"fieldPath": MOD_FIELD, "setToServerValue": "REQUEST_TIME"}],
            }
            if write.get("mask") is not None:
                paths = [quote_field_path(k) for k in write["mask"]] + [DEL_FIELD, BY_FIELD]
                op["updateMask"] = {"fieldPaths": paths}
            precondition = write.get("precondition")
            if precondition:
                op["currentDocument"] = precondition
            body.append(op)
        resp = self._request("POST", url, json={"writes": body})
        if resp.status_code == 200:
            out = []
            for write_result in resp.json().get("writeResults", []):
                transform_result = (write_result.get("transformResults") or [{}])[0]
                out.append({"update_time": write_result.get("updateTime"),
                            "modified_at": transform_result.get("timestampValue") or write_result.get("updateTime")})
            return out
        text = resp.text or ""
        if resp.status_code in (404, 409) or "FAILED_PRECONDITION" in text or "ALREADY_EXISTS" in text:
            raise FirestoreConflictError(f"commit HTTP {resp.status_code} - {text[:200]}")
        raise FirestoreError(f"commit HTTP {resp.status_code} - {text[:300]}")
