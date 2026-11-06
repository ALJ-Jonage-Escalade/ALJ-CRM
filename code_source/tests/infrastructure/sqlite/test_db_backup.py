"""SqliteDatabase.create_db_backup: local safety copy, pointless with Firestore (the cache is rebuilt from it)."""

import glob
import os
from unittest.mock import patch

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.connection import SqliteDatabase
from support.member_db import MemberDbTestCase


class TestCreateDbBackup(MemberDbTestCase):

    def _backups_after_call(self, firestore_enabled: bool) -> list[str]:
        with patch("infrastructure.sqlite.connection.ROOT_DIR", self._tmp.name), \
                patch.object(CloudDatabase, "is_enabled", return_value=firestore_enabled):
            SqliteDatabase.create_db_backup()
        return glob.glob(os.path.join(self._tmp.name, "archive", "db", "database_backup_*.db"))

    def test_create_db_backup_writes_a_copy_without_firestore(self):
        self.assertEqual(len(self._backups_after_call(firestore_enabled=False)), 1)

    def test_create_db_backup_writes_nothing_with_firestore(self):
        self.assertEqual(self._backups_after_call(firestore_enabled=True), [])
        self.assertFalse(os.path.exists(os.path.join(self._tmp.name, "archive")))
