"""
Tests unitaires pour l'application Web Mobile PWA (competitions.html, manifest, service worker).
"""

import os
import sys
import unittest
import json

_tests_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src_dir = os.path.join(os.path.dirname(_tests_dir), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)


from api.web.pages import get_competitions_management_page
from api.web.pwa import get_manifest, get_sw, get_web_version


class TestMobilePWA(unittest.TestCase):
    """Vérifie la conformité PWA et les fonctionnalités de l'interface mobile."""

    def test_manifest_endpoint(self):
        resp = get_manifest()
        self.assertEqual(resp.media_type, "application/manifest+json")
        self.assertTrue(os.path.exists(resp.path))
        with open(resp.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["name"], "ALJ Escalade — Compétitions")
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["theme_color"], "#1E293B")

    def test_service_worker_endpoint(self):
        resp = get_sw()
        self.assertEqual(resp.media_type, "application/javascript")
        self.assertTrue(os.path.exists(resp.path))
        with open(resp.path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertRegex(content, r'CACHE_NAME = "alj-escalade-v\d+"')
        self.assertIn("addEventListener(\"fetch\"", content)

    def test_web_version_matches_service_worker_cache(self):
        """La version affichée par la page doit suivre le nom du cache du service worker."""
        version = get_web_version()["web_version"]
        self.assertRegex(version, r"^\d+$")
        with open(get_sw().path, "r", encoding="utf-8") as f:
            sw = f.read()
        self.assertIn(f'CACHE_NAME = "alj-escalade-v{version}"', sw)
        with open(get_competitions_management_page().path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(f"(v{version})</title>", html)
        self.assertIn(f'id="web-version">v{version}<', html)

    def test_competitions_page_uses_api_only(self):
        """Competition data is read and written through the API, never Firestore directly."""
        with open(get_competitions_management_page().path, "r", encoding="utf-8") as f:
            html = f.read()
        for firestore_call in (".collection(", "onSnapshot", "runTransaction"):
            self.assertNotIn(firestore_call, html, firestore_call)
        self.assertIn('<script src="/static-web/alj-sync.js"></script>', html)
        for url in ("/api/competitions", "/api/coaches", "/api/competition-members",
                    "/api/helloasso/items"):
            self.assertIn(f'"{url}"', html, url)
        self.assertIn('<script src="/static-web/alj-store.js"></script>', html)

    def test_offline_store(self):
        """Phase 5: the phone keeps competitions, coaches and competitors' contacts in
        IndexedDB (alj-store.js only), wiped on logout and on loss of role."""
        web_dir = os.path.join(os.path.dirname(_tests_dir), "web")
        for root, _, files in os.walk(web_dir):
            for name in files:
                if not name.endswith((".html", ".js")):
                    continue
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if name != "alj-store.js":
                    # alj-firebase.js deletes the old Firestore SDK copy (firestore/*) only
                    self.assertNotIn("indexedDB.open(", content, path)
                    self.assertNotIn("alj_snapshot:", content, path)  # old localStorage snapshots
        with open(get_competitions_management_page().path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('const STORED_RESOURCES = ["competitions", "coaches", "competitors"];', html)
        self.assertIn('"/api/members/competitors"', html)
        self.assertIn('names.concat("competitors", "helloasso")', html)  # coaches only
        on_logout = html[html.index("auth.onAuthStateChanged"):html.index("/* ===================== Synchronisation")]
        self.assertIn("ALJStore.clearAll()", on_logout)
        on_denied = html[html.index("info.status === 401 || info.status === 403"):]
        self.assertLess(on_denied.index("roleLost()"), on_denied.index("setSyncInfo("))  # wipes the store
        with open(get_sw().path, "r", encoding="utf-8") as f:
            self.assertIn('"/static-web/alj-store.js"', f.read())
        with open(os.path.join(web_dir, "shared", "alj-store.js"), "r", encoding="utf-8") as f:
            store = f.read()
        self.assertIn("const MAX_AGE_DAYS = 30;", store)
        self.assertIn("navigator.storage.persist()", store)
        self.assertIn('await run("outbox", "readwrite", s => s.clear());', store)  # clearAll empties the outbox

    def test_offline_queue(self):
        """Phase 5b: only « Participe » on a listed competitor is queued offline, sent with the
        participant's updated_at (the server refuses it if the participant changed), and the
        outbox is wiped with the store."""
        with open(get_competitions_management_page().path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn(r"const QUEUED_URL = /^\/api\/competitions\/\d+\/participants\/\d+$/;", html)
        self.assertIn('const QUEUED_FLAGS = ["selectionne"];', html)
        self.assertEqual(html.count("queueFlag(c, existing,"), 2)  # offline before the request, or cut during it
        self.assertIn('unchanged_since: String(entry.unchanged_since || "")', html)
        flush = html[html.index("async function flushOutbox()"):html.index("/* Page active absente")]
        self.assertIn('"PATCH"', flush)
        self.assertIn("entry.uid === uid && QUEUED_URL.test(entry.url)", flush)
        self.assertIn("roleLost()", flush)  # 401/403 while sending
        role_lost = html[html.index("function roleLost()"):html.index("/* =====", html.index("function roleLost()"))]
        self.assertIn("ALJStore.clearAll()", role_lost)
        self.assertIn("outbox = new Map()", role_lost)
        logout = html[html.index("function logout()"):html.index("auth.onAuthStateChanged")]
        self.assertIn("confirm(", logout)  # unsent changes: warned before they are lost

    def test_competitions_html_pwa_and_email_features(self):
        resp = get_competitions_management_page()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(os.path.exists(resp.path))
        with open(resp.path, "r", encoding="utf-8") as f:
            html = f.read()

        # Vérifications PWA
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest">', html)
        self.assertIn('<meta name="theme-color" content="#1E293B">', html)
        self.assertIn("serviceWorker.register('/sw.js')", html)

        # Vérifications Envoi d'E-mails
        self.assertIn('id="p-email-btn"', html)
        self.assertIn('id="email-modal"', html)
        self.assertIn('id="em-template-select"', html)
        self.assertIn('id="em-preview-box"', html)
        self.assertIn('sendCampaignEmails()', html)

        # Vérifications Appel 1-clic téléphone
        self.assertIn('href="tel:', html)

        # Loading the « Compétition » group goes through the API (rule tested in tests/api)
        self.assertIn('compUrl(c.id, "/load-group")', html)

        # Vérifications Édition Compétition (navigation showPage, réinitialisation et retour)
        self.assertIn('showPage("comps");', html)
        self.assertIn('editSourcePage', html)
        self.assertIn('openParticipants(savedCompId)', html)

        # Vérifications Écran HelloAsso & Rattachement des paiements
        self.assertIn('data-page="helloasso"', html)
        self.assertIn('id="page-helloasso"', html)
        self.assertIn('id="ha-attach-modal"', html)
        self.assertIn('openAttachModal', html)
        self.assertIn('saveAttachment', html)
        self.assertIn('renderHelloAssoPage', html)
        self.assertIn('id="ha-items-list"', html)

        # Vérifications Mode Consultation (Lecture Seule) selon l'utilisateur
        self.assertIn('function isCoachUser()', html)
        self.assertIn('function isReadOnlyUser()', html)
        self.assertIn('function isAuthorizedUser()', html)
        self.assertIn('function applyRolePermissions()', html)
        self.assertIn('id="setup-role-badge"', html)
        self.assertIn('id="setup-unauthorized"', html)
        self.assertIn('id="comp-form-card"', html)

        # Vérifications Filtres et Récapitulatif Compétiteurs
        self.assertIn('id="p-kpi-participe"', html)
        self.assertIn('id="p-kpi-attente"', html)
        self.assertIn('id="p-kpi-paye"', html)
        self.assertIn('id="p-chip-selected"', html)
        self.assertIn('id="p-chip-unpaid"', html)
        self.assertIn('setParticipantFilter', html)
        self.assertIn('participantFilter', html)
        self.assertIn('en attente ·', html)


if __name__ == "__main__":
    unittest.main()
