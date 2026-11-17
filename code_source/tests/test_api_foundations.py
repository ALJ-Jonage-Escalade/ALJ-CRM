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
from api.admin import access
from api.auth import me
from api.competitions import coaches, competitions, email_log, helloasso_items, participants
from api.competitions import members as competition_members
from api.competitions import results
from api.integrations import helloasso_campaigns
from api.members import members, seasons
from api.responses import json_with_etag

SERVER_MODE = {"ALJ_API_AUTH": "off", "K_SERVICE": "alj-escalade-api"}


def concrete(path: str) -> str:
    """/api/competitions/{competition_id}/participants -> /api/competitions/7/participants"""
    return re.sub(r"\{[^}]+\}", "7", path)


def api_routes(*routers):
    return [r for router in routers for r in router.routes if isinstance(r, APIRoute)]


def app_routes(routes):
    """APIRoutes of the app, including those of the included routers (recent FastAPI keeps
    each included router as one node instead of copying its routes into the app)."""
    found = []
    for r in routes:
        included = getattr(r, "original_router", None)
        if included is not None:
            found += app_routes(included.routes)
        elif isinstance(r, APIRoute):
            found.append(r)
    return found


class TestSqliteCacheScope(unittest.TestCase):

    def test_uses_sqlite_cache(self):
        f = server.uses_sqlite_cache
        for path in ("/api/competitions", "/api/competitions/12/participants", "/api/coaches",
                     "/api/coaches/3", "/api/competition-members", "/api/helloasso/items",
                     "/api/helloasso/items/9/link", "/health", "/bureau/",
                     # MyCompet results batch: Firestore only (Cloud Scheduler deadline)
                     "/api/competitions/cron/fetch-results", "/api/competitions/12/fetch-results",
                     "/api/settings/competitions-results"):
            self.assertFalse(f(path), path)
        for path in ("/api/members", "/api/email-templates", "/api/helloasso/sync",
                     "/api/competitions-x", "/api/reports/map-points", "/api/reports/pivot-records",
                     # not a route of the Firestore-only routers, although under their prefix
                     "/api/competitions/12/route-future"):
            self.assertTrue(f(path), path)

    def test_every_firestore_router_route_skips_cache(self):
        routes = api_routes(competitions.router, participants.router, coaches.router,
                            competition_members.router, helloasso_items.router, results.router, email_log.router, me.router,
                            access.router, helloasso_campaigns.router)
        self.assertGreater(len(routes), 15)
        for r in routes:
            self.assertFalse(server.uses_sqlite_cache(concrete(r.path)), r.path)
        for r in api_routes(members.router, seasons.router):  # served from the SQLite cache
            self.assertTrue(server.uses_sqlite_cache(concrete(r.path)), r.path)

    def test_every_other_api_route_uses_cache(self):
        """Outside the Firestore-only routers, every /api/ route reads the SQLite cache (app
        settings, members…), whatever its prefix."""
        firestore_only = set(map(id, api_routes(competitions.router, participants.router, coaches.router,
                                                competition_members.router, helloasso_items.router, results.router,
                                                email_log.router, me.router, access.router, helloasso_campaigns.router)))
        routes = [r for r in app_routes(server.app.routes)
                  if id(r) not in firestore_only and r.path.startswith("/api/")]
        self.assertGreater(len(routes), 15)
        for r in routes:
            self.assertTrue(server.uses_sqlite_cache(concrete(r.path)), r.path)

    def test_firestore_only_routes_skip_cache_refresh(self):
        """A competition request must not wait for the SQLite cache (full rebuild on a cold start)."""
        client = TestClient(server.app)
        with patch.dict(os.environ, SERVER_MODE), \
                patch.object(server.CloudDatabase, "is_enabled", return_value=True), \
                patch.object(server.CloudDatabase, "ensure_fresh") as fresh, \
                patch.object(server.CloudDatabase, "after_write") as after, \
                patch("infrastructure.firestore.competitions.competitions.list_competition_docs", return_value=[]), \
                patch("infrastructure.firestore.competitions.participants.add_participant_doc", return_value=None), \
                patch("infrastructure.firestore.competitions.competitions.get_competition_doc", return_value=None):
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

    def test_results_cron_skips_cache_refresh(self):
        """Cloud Scheduler's call must not wait for a SQLite cache rebuild (cold start, 180 s deadline)."""
        report = {"status": "success", "executed_at": "2026-10-22T07:00:00", "competitions_checked": 0,
                  "competitions_updated": 0, "competitions_remaining": 0, "partial": False, "window_days": 30,
                  "email_sent": False, "notification_email": "n@example.org", "details": []}
        client = TestClient(server.app)
        with patch.dict(os.environ, SERVER_MODE), \
                patch.object(server.CloudDatabase, "is_enabled", return_value=True), \
                patch.object(server.CloudDatabase, "ensure_fresh") as fresh, \
                patch.object(server.CloudDatabase, "after_write") as after, \
                patch("services.competitions.results_batch.CompetitionResultsBatchService.run_daily_batch",
                      return_value=report) as job:
            r = client.post("/api/competitions/cron/fetch-results")
            self.assertEqual(r.status_code, 200, r.text)
            job.assert_called_once()
            fresh.assert_not_called()
            after.assert_not_called()
        self.assertEqual(r.json(), report)

    def test_cache_write_runs_on_refreshed_cache(self):
        r = self._assert_cache_around(
            "DELETE", "/api/planning/item/12",
            "api.activities.planning.PlanningRepository.delete_planning_item",
            True)
        self.assertEqual(r.json()["status"], "success")

    def test_write_not_replicated_keeps_success_and_flags_header(self):
        """A write saved in the cache but not sent to Firestore stays a success (it happened, a retry would repeat it)
        and is flagged by a header."""
        client = TestClient(server.app)
        with patch.dict(os.environ, SERVER_MODE), \
                patch.object(server.CloudDatabase, "is_enabled", return_value=True), \
                patch.object(server.CloudDatabase, "ensure_fresh"), \
                patch.object(server.CloudDatabase, "after_write", side_effect=[True, False]), \
                patch("api.activities.planning.PlanningRepository.delete_planning_item", return_value=True), \
                self.assertLogs("alj", "ERROR"):
            replicated = client.delete("/api/planning/item/12")
            pending = client.delete("/api/planning/item/12")
        self.assertNotIn(server.REPLICATION_PENDING_HEADER, replicated.headers)
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.headers[server.REPLICATION_PENDING_HEADER], "1")


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
        self.assertRegex(etag, r'^"[0-9a-f]{64}"$')
        r2 = client.get("/data", headers={"If-None-Match": etag})
        self.assertEqual(r2.status_code, 304)
        self.assertEqual(r2.content, b"")
        self.assertEqual(r2.headers["etag"], etag)
        self.assertEqual(client.get("/data", headers={"If-None-Match": f'"x", W/{etag}'}).status_code, 304)
        self.assertEqual(client.get("/data", headers={"If-None-Match": '"autre"'}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
