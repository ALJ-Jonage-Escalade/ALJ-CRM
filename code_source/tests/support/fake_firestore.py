"""In-memory stand-in for FirestoreClient, shared by the repository and API tests."""

import unittest
from unittest.mock import patch

from infrastructure.firestore.client import FirestoreClient
from infrastructure.firestore import client as fc
from infrastructure.firestore.competitions import member_directory
from infrastructure.firestore.competitions import documents


class FakeFirestore:
    """Magasin de documents en mémoire imitant FirestoreClient."""

    META = ("_doc_id", "_update_time")

    def __init__(self):
        self.store = {}
        # Horodatage de version par document (imite `updateTime` de Firestore)
        self.versions = {}
        self._clock = 0
        # Crochet optionnel appelé juste avant une écriture conditionnelle
        # (simule une modification concurrente entre lecture et écriture).
        self.before_conditional_write = None

    def _col(self, collection_name):
        return self.store.setdefault(collection_name, {})

    def _touch(self, collection_name, doc_id):
        self._clock += 1
        self.versions[(collection_name, str(doc_id))] = f"2026-01-01T00:00:00.{self._clock:06d}Z"

    def _out(self, collection_name, doc_id, doc):
        out = dict(doc)
        out["_doc_id"] = str(doc_id)
        out["_update_time"] = self.versions.get((collection_name, str(doc_id)))
        return out

    def get_document(self, collection_name, doc_id, project_id=None, access_token=None):
        doc = self._col(collection_name).get(str(doc_id))
        if doc is None:
            return None
        return self._out(collection_name, doc_id, doc)

    def list_documents(self, collection_name, project_id=None, access_token=None):
        return [self._out(collection_name, doc_id, doc)
                for doc_id, doc in self._col(collection_name).items()]

    def list_latest(self, collection_name, field, limit, project_id=None, access_token=None):
        docs = [self._out(collection_name, doc_id, doc) for doc_id, doc in self._col(collection_name).items() if field in doc]
        return sorted(docs, key=lambda doc: doc[field], reverse=True)[:limit]

    def upsert_document(self, collection_name, doc_id, data, project_id=None, access_token=None):
        self._col(collection_name)[str(doc_id)] = {k: v for k, v in data.items() if k not in self.META}
        self._touch(collection_name, doc_id)
        return True

    def create_document(self, collection_name, doc_id, data, project_id=None, access_token=None):
        if str(doc_id) in self._col(collection_name):
            return False
        return self.upsert_document(collection_name, doc_id, data)

    def update_fields(self, collection_name, doc_id, patch, project_id=None, access_token=None,
                      expected_update_time=None):
        if expected_update_time:
            hook = self.before_conditional_write
            if hook:
                hook(collection_name, doc_id)
            if self.versions.get((collection_name, str(doc_id))) != expected_update_time:
                raise fc.FirestoreConflictError("conflit simulé")
        doc = self._col(collection_name).setdefault(str(doc_id), {})
        doc.update({k: v for k, v in patch.items() if k not in self.META})
        self._touch(collection_name, doc_id)
        return True

    def delete_document(self, collection_name, doc_id, project_id=None, access_token=None):
        return self._col(collection_name).pop(str(doc_id), None) is not None

    def batch_upsert(self, writes, project_id=None, access_token=None):
        for w in writes:
            col, _, doc_id = str(w["path"]).partition("/")
            data = {k: v for k, v in (w.get("data") or {}).items() if k != "_doc_id"}
            mask = w.get("update_fields")
            if mask:  # updateMask : seuls les champs listés sont écrits
                doc = dict(self._col(col).get(doc_id) or {})
                for k in mask:
                    if k in data:
                        doc[k] = data[k]
                    else:
                        doc.pop(k, None)
                data = doc
            self._col(col)[doc_id] = data
        return {"written": len(writes), "errors_count": 0, "errors": []}


def use_fake_firestore(test: unittest.TestCase) -> FakeFirestore:
    """Replace FirestoreClient by an in-memory store for the duration of `test`."""
    fake = FakeFirestore()
    for name in ("get_document", "list_documents", "list_latest", "upsert_document", "create_document", "update_fields",
                 "delete_document", "batch_upsert"):
        p = patch.object(FirestoreClient, name, getattr(fake, name))
        p.start()
        test.addCleanup(p.stop)
    return fake


class FirestoreRepoTestCase(unittest.TestCase):
    """Base commune : FirestoreClient remplacé par le magasin en mémoire."""

    def setUp(self):
        self.fake = use_fake_firestore(self)
        # Cache adhérents remis à zéro entre les tests
        member_directory.invalidate_cache()
        self.addCleanup(member_directory.invalidate_cache)

    def seed_adherent(self, aid, nom="MARTIN", prenom="Lucas", licence="654321",
                      tarif="Compétition U18", email="lucas.martin@test.fr", statut="Terminé", **extra):
        documents.COLLECTION_ADHERENTS and self.fake.upsert_document(
            documents.COLLECTION_ADHERENTS, str(aid),
            {
                "id": aid, "nom": nom, "prenom": prenom, "licence_ffme": licence,
                "num_licence": licence, "email": email, "phone": "0600000000",
                "tarif": tarif, "statut": statut, "creneau_groupe": tarif, "emergency_name": "Mère",
                "emergency_phone": "0611111111", **extra,
            },
        )
        member_directory.invalidate_cache()
