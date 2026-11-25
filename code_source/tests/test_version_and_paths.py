import os
import unittest

# Ajustement du chemin pour importer les modules depuis 'src'

from paths import CODE_ROOT, data_root
from domain.constants import APP_VERSION


class TestVersionAndPaths(unittest.TestCase):
    """Fondations de la distribution : fichier VERSION (lu par l'updater) et
    séparation du dossier de données stables (data/) du code source."""

    def test_version_file_matches_app_version(self):
        """Le fichier VERSION (référence de l'updater) est aligné sur APP_VERSION."""
        version_path = os.path.join(CODE_ROOT, "VERSION")
        self.assertTrue(os.path.exists(version_path), "Fichier VERSION introuvable dans code_source/")
        with open(version_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), APP_VERSION)

    def test_data_root_is_separate_from_code_root(self):
        """data/ (cache SQLite, fichiers utilisateurs) vit en dehors du code source :
        une mise à jour de l'app ne doit jamais toucher les données."""
        self.assertNotEqual(data_root(), os.path.abspath(CODE_ROOT))
        self.assertFalse(data_root().startswith(CODE_ROOT + os.sep))


if __name__ == "__main__":
    unittest.main()
