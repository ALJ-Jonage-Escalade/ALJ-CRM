"""FirestoreClient REST calls: batch commit body, update preconditions, metadata keys never written."""

import unittest
from unittest.mock import MagicMock, patch
from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore import client as fc


class TestBatchUpsertCommitBody(unittest.TestCase):
    """Régression : :commit exige un nom de document RELATIF (projects/…/documents/…),
    pas une URL complète (HTTP 400 « lacks projects » vu en production)."""

    def test_commit_uses_relative_document_name(self):
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(FirestoreClient, "get_access_token", return_value="fake-token"):
            resp = mock_post.return_value
            resp.status_code = 200
            report = FirestoreClient.batch_upsert(
                [{"path": "adherents/131", "data": {"nom": "DUPONT"}}],
                project_id="smart-amplifier-510811-n6",
            )
        self.assertEqual(report["written"], 1)
        self.assertEqual(report["errors_count"], 0)
        body = mock_post.call_args.kwargs["json"]
        name = body["writes"][0]["update"]["name"]
        self.assertTrue(name.startswith("projects/"), name)
        self.assertEqual(
            name,
            "projects/smart-amplifier-510811-n6/databases/(default)/documents/adherents/131",
        )
        # Le :commit est bien appelé sur l'URL absolue du service
        self.assertIn("https://firestore.googleapis.com/v1/", mock_post.call_args.args[0])
        self.assertIn(":commit", mock_post.call_args.args[0])


class TestFirestoreClientPrecondition(unittest.TestCase):
    """Client REST : précondition `currentDocument.updateTime` et clés techniques."""

    def test_meta_keys_jamais_ecrites(self):
        fields = fc.dict_to_firestore_fields({"nom": "A", "_doc_id": "1", "_update_time": "t"})
        self.assertEqual(list(fields), ["nom"])

    def test_update_fields_envoie_la_precondition(self):
        """Precondition in the body of a :commit (the URL parameter is ignored by the emulator)."""
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            mock_post.return_value.status_code = 200
            FirestoreClient.update_fields("competitions", "1", {"x": 1, "_update_time": "T"},
                                          project_id="p", expected_update_time="T0")
        self.assertTrue(mock_post.call_args.args[0].endswith("/projects/p/databases/(default)/documents:commit"))
        write = mock_post.call_args.kwargs["json"]["writes"][0]
        self.assertEqual(write["currentDocument"], {"updateTime": "T0"})
        self.assertEqual(write["updateMask"], {"fieldPaths": ["x"]})
        self.assertEqual(write["update"]["name"], "projects/p/databases/(default)/documents/competitions/1")
        self.assertEqual(list(write["update"]["fields"]), ["x"])

    def test_update_fields_without_precondition_uses_patch(self):
        with patch.object(fc.requests, "patch") as mock_patch, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            mock_patch.return_value.status_code = 200
            FirestoreClient.update_fields("competitions", "1", {"x": 1}, project_id="p")
        params = mock_patch.call_args.kwargs["params"]
        self.assertEqual(params, [("updateMask.fieldPaths", "x")])

    def test_update_fields_conflit(self):
        with patch.object(fc.requests, "post") as mock_post, \
             patch.object(fc.requests, "patch") as mock_patch, \
             patch.object(FirestoreClient, "get_access_token", return_value="tok"):
            for mock in (mock_post, mock_patch):
                mock.return_value.status_code = 400
                mock.return_value.text = '{"error": {"status": "FAILED_PRECONDITION"}}'
            with self.assertRaises(fc.FirestoreConflictError):
                FirestoreClient.update_fields("competitions", "1", {"x": 1},
                                              project_id="p", expected_update_time="T0")
            # Sans précondition, une erreur 400 reste une erreur générique
            with self.assertRaises(fc.FirestoreError) as ctx:
                FirestoreClient.update_fields("competitions", "1", {"x": 1}, project_id="p")
            self.assertNotIsInstance(ctx.exception, fc.FirestoreConflictError)


def _response(status_code, payload=None, text=""):
    resp = MagicMock(status_code=status_code, text=text)
    resp.json.return_value = payload
    return resp


DOC = {"name": "projects/p/databases/(default)/documents/competitions/7",
       "fields": {"nom": {"stringValue": "Coupe"}}, "updateTime": "T1"}
FLAT_DOC = {"nom": "Coupe", "_doc_id": "7", "_update_time": "T1"}


class TestFirestoreClientStatusMapping(unittest.TestCase):
    """HTTP answers mapped to results: absent document, already existing, errors, unreachable Firestore."""

    def setUp(self):
        patcher = patch.object(FirestoreClient, "get_access_token", return_value="tok")
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, method, response, action):
        with patch.object(fc.requests, method, return_value=response) as mock:
            return action(), mock

    def test_get_document(self):
        self.assertEqual(self.call("get", _response(200, DOC), lambda: FirestoreClient.get_document("competitions", "7", "p"))[0],
                         FLAT_DOC)
        self.assertIsNone(self.call("get", _response(404), lambda: FirestoreClient.get_document("competitions", "7", "p"))[0])
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 500"):
            self.call("get", _response(500), lambda: FirestoreClient.get_document("competitions", "7", "p"))

    def test_list_documents_follows_pages(self):
        pages = [_response(200, {"documents": [DOC], "nextPageToken": "next"}), _response(200, {})]
        with patch.object(fc.requests, "get", side_effect=pages) as mock_get:
            self.assertEqual(FirestoreClient.list_documents("competitions", "p"), [FLAT_DOC])
        self.assertEqual(mock_get.call_args.kwargs["params"], {"pageSize": 300, "pageToken": "next"})
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 403"):
            self.call("get", _response(403), lambda: FirestoreClient.list_documents("competitions", "p"))

    def test_queries_keep_only_rows_with_a_document(self):
        rows = [{"readTime": "T"}, {"document": DOC}]
        result, mock_post = self.call("post", _response(200, rows),
                                      lambda: FirestoreClient.list_equal("competitions", "saison", "2026", "p"))
        self.assertEqual(result, [FLAT_DOC])
        query = mock_post.call_args.kwargs["json"]["structuredQuery"]
        self.assertEqual(query["where"]["fieldFilter"]["value"], {"stringValue": "2026"})
        result, mock_post = self.call("post", _response(200, rows),
                                      lambda: FirestoreClient.list_latest("competitions", "date", 5, "p"))
        self.assertEqual(mock_post.call_args.kwargs["json"]["structuredQuery"]["limit"], 5)
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 400"):
            self.call("post", _response(400), lambda: FirestoreClient.list_containing("competitions", "ids", 1, "p"))

    def test_create_document_never_overwrites(self):
        self.assertTrue(self.call("post", _response(200), lambda: FirestoreClient.create_document("c", "1", {"x": 1}, "p"))[0])
        self.assertFalse(self.call("post", _response(409), lambda: FirestoreClient.create_document("c", "1", {"x": 1}, "p"))[0])
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 500"):
            self.call("post", _response(500), lambda: FirestoreClient.create_document("c", "1", {"x": 1}, "p"))

    def test_upsert_document(self):
        self.assertTrue(self.call("patch", _response(200), lambda: FirestoreClient.upsert_document("c", "1", {"x": 1}, "p"))[0])
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 403"):
            self.call("patch", _response(403), lambda: FirestoreClient.upsert_document("c", "1", {"x": 1}, "p"))

    def test_update_fields_with_only_metadata_writes_nothing(self):
        with patch.object(fc.requests, "patch") as mock_patch:
            self.assertFalse(FirestoreClient.update_fields("c", "1", {"_doc_id": "1"}, "p"))
        mock_patch.assert_not_called()

    def test_delete_document(self):
        self.assertTrue(self.call("delete", _response(200), lambda: FirestoreClient.delete_document("c", "1", "p"))[0])
        self.assertFalse(self.call("delete", _response(404), lambda: FirestoreClient.delete_document("c", "1", "p"))[0])
        with self.assertRaisesRegex(fc.FirestoreError, "HTTP 500"):
            self.call("delete", _response(500), lambda: FirestoreClient.delete_document("c", "1", "p"))

    def test_unreachable_firestore_is_a_firestore_error(self):
        with patch.object(fc.requests, "get", side_effect=fc.requests.ConnectionError("down")), \
                self.assertRaisesRegex(fc.FirestoreError, "injoignable"):
            FirestoreClient.get_document("c", "1", "p")

    def test_batch_upsert_counts_failed_chunks(self):
        writes = [{"path": f"c/{number}", "data": {"x": number}, "update_fields": ["x"]}
                  for number in range(fc.BATCH_WRITE_LIMIT + 1)]
        answers = [_response(500, text="INTERNAL"), fc.requests.ConnectionError("down")]
        with patch.object(fc.requests, "post", side_effect=answers) as mock_post:
            report = FirestoreClient.batch_upsert(writes, project_id="p")
        self.assertEqual(report["written"], 0)
        self.assertEqual(report["errors_count"], fc.BATCH_WRITE_LIMIT + 1)
        self.assertEqual(len(report["errors"]), 2)
        self.assertEqual(mock_post.call_args_list[0].kwargs["json"]["writes"][0]["updateMask"], {"fieldPaths": ["x"]})


class TestFirestoreClientAccessToken(unittest.TestCase):
    """On Cloud Run the token comes from the metadata server; it falls back to the club's OAuth2 when that fails."""

    def test_cloud_run_uses_the_metadata_server(self):
        with patch.object(fc.runtime_env, "is_cloud_run", return_value=True), \
                patch.object(fc.requests, "get", return_value=_response(200, {"access_token": "meta"})), \
                patch.object(fc.GoogleDriveClient, "get_access_token") as oauth:
            self.assertEqual(FirestoreClient.get_access_token(), "meta")
        oauth.assert_not_called()

    def test_cloud_run_falls_back_to_oauth_when_metadata_fails(self):
        with patch.object(fc.runtime_env, "is_cloud_run", return_value=True), \
                patch.object(fc.requests, "get", side_effect=fc.requests.ConnectionError("down")), \
                patch.object(fc.GoogleDriveClient, "get_access_token", return_value="oauth"):
            self.assertEqual(FirestoreClient.get_access_token(), "oauth")
