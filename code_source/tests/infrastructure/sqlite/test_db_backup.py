"""SqliteDatabase.create_db_backup: local safety copy, before the FFME import changes a database of its own; pointless
with Firestore (the cache is rebuilt from it)."""

import glob
import io
import os
from unittest.mock import patch

import openpyxl

from infrastructure.firestore.cloud_database import CloudDatabase
from infrastructure.sqlite.connection import SqliteDatabase
from services.members import ffme
from support.member_db import MemberDbTestCase


class TestCreateDbBackup(MemberDbTestCase):

    def _backups(self) -> list[str]:
        return glob.glob(os.path.join(self._tmp.name, "archive", "db", "database_backup_*.db"))

    def test_create_db_backup_writes_a_copy(self):
        with patch("infrastructure.sqlite.connection.ROOT_DIR", self._tmp.name):
            SqliteDatabase.create_db_backup()
        self.assertEqual(len(self._backups()), 1)

    def test_ffme_import_backs_up_only_without_firestore(self):
        self.seed("1", "Léo", "MARTIN", "Cours ados")
        for firestore_enabled, backups, licence in ((True, 0, "112233"), (False, 1, "445566")):  # each import changes the licence
            workbook = openpyxl.Workbook()
            workbook.active.append(["Nom", "Prénom", "N° de licence"])
            workbook.active.append(["MARTIN", "Léo", licence])
            buffer = io.BytesIO()
            workbook.save(buffer)
            with self.subTest(firestore_enabled=firestore_enabled), \
                    patch("infrastructure.sqlite.connection.ROOT_DIR", self._tmp.name), \
                    patch.object(CloudDatabase, "is_enabled", return_value=firestore_enabled):
                ffme.apply_import("2026-2027", buffer.getvalue())
            self.assertEqual(len(self._backups()), backups)
