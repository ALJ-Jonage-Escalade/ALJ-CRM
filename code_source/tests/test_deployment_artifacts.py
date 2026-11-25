"""
Deployment artifacts (pyproject, requirements, Dockerfile, .dockerignore, scripts) and the production routes
the deploy relies on (health check, HelloAsso webhook ping, root redirect).
"""

import os
import unittest

from paths import CODE_ROOT
from domain.constants import APP_VERSION, get_active_season
from api.web.health import health_check
from api.web.pages import root_route
from api.integrations.helloasso import webhook_helloasso_ping


class TestDeploymentArtifacts(unittest.TestCase):
    """Vérifie la conformité des artefacts conteneurisés et des routes de production."""

    def test_dockerfile_python_matches_python_version_file(self):
        """The image runs the Python of .python-version (also read by the CI)."""
        with open(os.path.join(CODE_ROOT, ".python-version"), encoding="utf-8") as f:
            expected = f.read().strip()
        with open(os.path.join(CODE_ROOT, "Dockerfile"), encoding="utf-8") as f:
            content = f.read()
        self.assertIn(f"FROM python:{expected}-slim", content,
                      "Update the FROM line of the Dockerfile together with .python-version.")

    def test_dockerignore_security(self):
        """Vérifie que les secrets et fichiers de données sont rigoureusement exclus."""
        ignore_path = os.path.join(CODE_ROOT, ".dockerignore")
        self.assertTrue(os.path.isfile(ignore_path), ".dockerignore doit exister.")
        with open(ignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".env", content)
        self.assertIn("*.db", content)
        self.assertIn("venv/", content)

    def test_health_check_endpoint(self):
        """Vérifie le retour JSON de l'endpoint /health."""
        data = health_check()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "alj-escalade-api")
        self.assertEqual(data["version"], APP_VERSION)
        self.assertEqual(data["season"], get_active_season())
        self.assertIn("timestamp", data)

    def test_webhook_helloasso_ping_endpoint(self):
        """Vérifie le retour HTTP 200 de l'endpoint probe GET /webhooks/helloasso."""
        data = webhook_helloasso_ping()
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["endpoint"], "helloasso-webhook-receiver")
        self.assertIn("Payment", data["supported_events"])
        self.assertIn("Order", data["supported_events"])

    def test_root_route_redirect(self):
        """Vérifie que la route racine redirige vers /competitions ou renvoie les liens API."""
        resp = root_route()
        if hasattr(resp, "status_code"):
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/competitions", resp.headers.get("location", ""))
        else:
            self.assertIn("service", resp)
            self.assertIn("version", resp)


if __name__ == "__main__":
    unittest.main()
