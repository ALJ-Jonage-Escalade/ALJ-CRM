import os
import unittest
import hashlib
import shutil
import sqlite3
import tempfile
import pathlib

from paths import CODE_ROOT

_test_dir = os.path.join(CODE_ROOT, "tests")

# Fixture de référence (données personnelles : ignorée par git, poste local uniquement)
REFERENCE = os.path.join(_test_dir, "fixtures", "import_ffme_reference.csv")


class TestFFMEGoldenMaster(unittest.TestCase):
    """
    Test de non-régression octet à octet : l'export CSV FFME régénéré depuis
    un snapshot figé de database.db doit être STRICTEMENT identique au fichier
    de référence import_ffme_20260830_173135.csv.

    Ce test est le gate de validation de la migration BDD (phases 0 à 6).
    La fixture contient des données personnelles : elle est ignorée par git
    (voir .gitignore) et ne vit que sur le poste local.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REFERENCE):
            raise unittest.SkipTest(
                "Fixture de référence absente (tests/fixtures/import_ffme_reference.csv). "
                "Copier exports/ffme/import_ffme_20260830_173135.csv vers ce chemin pour activer le test."
            )

    def test_export_ffme_identique_reference(self):
        from infrastructure.sqlite.connection import SqliteDatabase
        from infrastructure.sqlite.members import MemberRepository
        from exports.membership_excel import generate_ffme_csv
        from paths import data_root

        db_live = os.path.join(data_root(), "database.db")
        self.assertTrue(os.path.exists(db_live), "database.db introuvable dans data/ (cache local)")

        tmpdir = tempfile.mkdtemp(prefix="alj_golden_test_")
        try:
            # 1. Snapshot cohérent de la base (API backup : inclut le contenu WAL)
            tmp_db = os.path.join(tmpdir, "database.db")
            uri_source = f"{pathlib.Path(db_live).as_uri()}?mode=ro"
            src = sqlite3.connect(uri_source, uri=True)
            dst = sqlite3.connect(tmp_db)
            src.backup(dst)
            dst.close()
            src.close()

            self._copy_contact_columns_to_table(tmp_db)

            # 2. Chargement via le chemin applicatif réel, sur la copie uniquement
            ancien_path = SqliteDatabase.get_db_path()
            SqliteDatabase.set_db_path(tmp_db)
            try:
                raw_data = MemberRepository.list_flat_member_rows("2026-2027")
            finally:
                SqliteDatabase.set_db_path(ancien_path)
            self.assertTrue(raw_data, "Aucune donnée chargée depuis la copie de la base")

            # 3. Génération vers un chemin dédié (aucune écriture dans exports/)
            out_csv = os.path.join(tmpdir, "import_ffme_test.csv")
            generate_ffme_csv(raw_data, output_path=out_csv)

            # 4. Comparaison stricte octet à octet
            with open(out_csv, "rb") as f:
                genere = f.read()
            with open(REFERENCE, "rb") as f:
                reference = f.read()

            if genere != reference:
                self.fail(self._diagnostic(genere, reference))
            self.assertEqual(
                hashlib.sha256(genere).hexdigest(),
                hashlib.sha256(reference).hexdigest(),
                "L'export CSV FFME diffère de la référence (SHA-256).",
            )
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _copy_contact_columns_to_table(path):
        """A snapshot taken before plans/emergency-contacts.md holds the contacts in the users columns only:
        they are copied to the emergency_contacts table, on the copy of the base."""
        from domain.members.emergency_contacts import missing_contacts
        from infrastructure.sqlite import schema_v2

        conn = sqlite3.connect(path)
        try:
            schema_v2.ensure_v2_schema(conn.cursor())
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            if "emergency1_name" not in columns or conn.execute("SELECT 1 FROM emergency_contacts LIMIT 1").fetchone():
                return
            for user_id, name1, phone1, name2, phone2 in conn.execute(
                    "SELECT id, emergency1_name, emergency1_phone, emergency2_name, emergency2_phone FROM users").fetchall():
                incoming = [{"name": name1, "phone": phone1}, {"name": name2, "phone": phone2}]
                for position, contact in enumerate(missing_contacts([], incoming)):
                    conn.execute("INSERT INTO emergency_contacts (user_id, name, phone, position) VALUES (?, ?, ?, ?)",
                                 (user_id, contact.name, contact.phone, position))
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _diagnostic(genere, reference):
        """Produit un diff lisible ligne/colonne en cas d'échec de la comparaison."""
        lignes_g = genere.decode("utf-8", "replace").splitlines()
        lignes_r = reference.decode("utf-8", "replace").splitlines()
        msg = [f"DIFF : {len(lignes_g)} lignes générées vs {len(lignes_r)} lignes de référence"]
        entetes = lignes_r[0].split(";") if lignes_r else []

        if len(lignes_g) != len(lignes_r):
            n = min(len(lignes_g), len(lignes_r))
            if lignes_g[:n] == lignes_r[:n]:
                sens = "en trop" if len(lignes_g) > len(lignes_r) else "manquantes"
                surplus = lignes_g[n:] if len(lignes_g) > len(lignes_r) else lignes_r[n:]
                msg.append(f"Les {n} premières lignes sont identiques ; "
                           f"{abs(len(lignes_g) - len(lignes_r))} ligne(s) {sens} :")
                for line in surplus[:5]:
                    msg.append(f"  {line[:130]}")
                return "\n".join(msg)

        for i, (a, b) in enumerate(zip(lignes_g, lignes_r, strict=False)):
            if a != b:
                msg.append(f"Première différence à la ligne {i + 1} :")
                if i == 0:
                    msg.append(f"  entête générée  : {a}")
                    msg.append(f"  entête référence: {b}")
                else:
                    cols_a = a.split(";")
                    cols_b = b.split(";")
                    for j in range(max(len(cols_a), len(cols_b))):
                        va = cols_a[j] if j < len(cols_a) else "<absent>"
                        vb = cols_b[j] if j < len(cols_b) else "<absent>"
                        if va != vb:
                            nom = entetes[j] if j < len(entetes) else f"colonne {j}"
                            msg.append(f"  colonne '{nom}' : '{va}' vs attendu '{vb}'")
                break
        return "\n".join(msg)


if __name__ == "__main__":
    unittest.main()
