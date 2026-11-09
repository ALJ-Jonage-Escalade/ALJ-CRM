"""FirestoreClient REST calls: batch commit body, update preconditions, metadata keys never written."""

import unittest
from unittest.mock import patch
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
