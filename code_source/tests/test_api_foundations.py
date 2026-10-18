"""Foundations of the API-only front end: SQLite middleware scope and ETag responses."""

import os
import re
import sys
import unittest
from unittest.mock import patch

_src_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import server
from api import coaches, competition_members, competitions, helloasso_items, members, participants, seasons
from api.responses import json_with_etag

SERVER_MODE = {"ALJ_API_AUTH": "off", "K_SERVICE": "alj-escalade-api"}


def concrete(path: str) -> str:
    """/api/competitions/{competition_id}/participants -> /api/competitions/7/participants"""
    return re.sub(r"\{[^}]+\}", "7", path)


def api_routes(*routers):
    return [r for router in routers for r in router.routes if isinstance(r, APIRoute)]


class TestSqliteCacheScope(unittest.TestCase):

    def test_uses_sqlite_cache(self):
        f = server.uses_sqlite_cache
        for path in ("/api/competitions", "/api/competitions/12/participants", "/api/coaches",
                     "/api/coaches/3", "/api/competition-members", "/api/helloasso/items",
                     "/api/helloasso/items/9/link", "/health", "/bureau/"):
            self.assertFalse(f(path), path)
        for path in ("/api/members", "/api/email-templates", "/api/helloasso/sync",
                     "/api/competitions-x", "/map", "/pivot",
                     # old routes of server.py under the Firestore prefixes: they use the cache
                     "/api/competitions/cron/fetch-results", "/api/competitions/12/check-all-paid",
                     "/api/competitions/12/fetch-results"):
            self.assertTrue(f(path), path)

    def test_every_firestore_router_route_skips_cache(self):
        routes = api_routes(competitions.router, participants.router, coaches.router,
                            competition_members.router, helloasso_items.router)
        self.assertGreater(len(routes), 15)
        for r in routes:
            self.assertFalse(server.uses_sqlite_cache(concrete(r.path)), r.path)
        for r in api_routes(members.router, seasons.router):  # served from the SQLite cache
            self.assertTrue(server.uses_sqlite_cache(concrete(r.path)), r.path)

    def test_every_api_route_of_server_py_uses_cache(self):
        """The routes left in server.py read the SQLite cache (app settings, members…), whatever
        their prefix: a new Firestore-only route belongs in a router of src/api/."""
        routes = [r for r in server.app.routes if isinstance(r, APIRoute)
                  and r.endpoint.__module__ == "server" and r.path.startswith("/api/")]
        self.assertIn("/api/competitions/cron/fetch-results", [r.path for r in routes])
        for r in routes:
            self.assertTrue(server.uses_sqlite_cache(concrete(r.path)), r.path)

    def test_firestore_only_routes_skip_cache_refresh(self):
        """A competition request must not wait for the SQLite cache (full rebuild on a cold start)."""
        client = TestClient(server.app)
        with patch.dict(os.environ, SERVER_MODE), \
                patch.object(server.CloudDatabase, "is_enabled", return_value=True), \
                patch.object(server.CloudDatabase, "ensure_fresh") as fresh, \
                patch.object(server.CloudDatabase, "after_write") as after, \
                patch("infrastructure.competition_firestore_repository.CompetitionFirestoreRepository.list_competition_docs", return_value=[]), \
                patch("infrastructure.competition_firestore_repository.CompetitionFirestoreRepository.get_competition_doc", return_value=None):
            client.get("/api/competitions")
            client.post("/api/competitions/1/participants", json={"adherent_id": 2})
            fresh.assert_not_called()
            after.assert_not_called()
            client.get("/api/route-inconnue")
            fresh.assert_called_once()

    def _assert_cache_around(self, method: str, url: str, target: str, result):
        """`target` runs on a refreshed cache, and its writes are sent to Firestore after it."""
        client = TestClient(server.app)
        with patch.dict(os.environ, SERVER_MODE), \
                patch.object(server.CloudDatabase, "is_enabled", return_value=True), \
                patch.object(server.CloudDatabase, "ensure_fresh") as fresh, \
                patch.object(server.CloudDatabase, "after_write") as after, \
                patch(target) as job:
            seen = {}
            job.side_effect = lambda *a, **k: seen.update(fresh=fresh.called, after=after.called) or result
            r = client.request(method, url)
            self.assertEqual(r.status_code, 200, r.text)
            job.assert_called_once()
            self.assertEqual(seen, {"fresh": True, "after": False})
            fresh.assert_called_once()
            after.assert_called_once()
        return r

    def test_results_cron_runs_on_refreshed_cache(self):
        """The cron reads the notification address and writes last_run/status in the SQLite cache."""
        r = self._assert_cache_around(
            "POST", "/api/competitions/cron/fetch-results",
            "infrastructure.competition_results_batch_service.CompetitionResultsBatchService.run_daily_batch",
            {"status": "success"})
        self.assertEqual(r.json(), {"status": "success"})

    def test_check_all_paid_runs_on_refreshed_cache(self):
        r = self._assert_cache_around(
            "POST", "/api/competitions/12/check-all-paid",
            "infrastructure.helloasso_webhook_service.HelloAssoWebhookService.check_and_notify_all_paid",
            True)
        self.assertEqual(r.json(), {"status": "success", "competition_id": 12, "notified": True})


def _app():
    app = FastAPI()

    @app.get("/data")
    def data(request: Request):
        return json_with_etag(request, {"nom": "Épreuve", "ids": [1, 2]})

    return TestClient(app)


class TestJsonWithEtag(unittest.TestCase):

    def test_etag_and_not_modified(self):
        client = _app()
        r = client.get("/data")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"nom": "Épreuve", "ids": [1, 2]})
        self.assertEqual(r.headers["cache-control"], "no-store")
        etag = r.headers["etag"]
        self.assertRegex(etag, r'^"[0-9a-f]{40}"$')
        r2 = client.get("/data", headers={"If-None-Match": etag})
        self.assertEqual(r2.status_code, 304)
        self.assertEqual(r2.content, b"")
        self.assertEqual(r2.headers["etag"], etag)
        self.assertEqual(client.get("/data", headers={"If-None-Match": f'"x", W/{etag}'}).status_code, 304)
        self.assertEqual(client.get("/data", headers={"If-None-Match": '"autre"'}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
