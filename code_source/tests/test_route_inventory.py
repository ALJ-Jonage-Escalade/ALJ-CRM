"""Route inventory of the app: moving routes between modules must not add, drop or rename any URL.

External callers depend on these exact paths: Cloud Scheduler (`batch-resultats-competitions`,
POST /api/competitions/cron/fetch-results every day at 07:00), the HelloAsso webhook, the Google
OAuth redirect URIs, the deploy health check and the installed PWAs.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Optional

from starlette.routing import BaseRoute, Mount, Route

import server
from infrastructure.security.api_auth import PUBLIC_PATHS, required_role
from infrastructure.security.roles import Role

# (method, path) of every route -> the role it requires (None: public; "MOUNT" for the static file mounts, None too).
# HEAD is left out (Starlette adds it to every GET). A new route must be added here with its role: writes default to
# coach in api_auth.required_role, so an admin-only write needs its own branch there.
EXPECTED_ROUTES: dict[tuple[str, str], Optional[Role]] = {
    ("GET", "/"): None,
    ("MOUNT", "/annuaire"): None,
    ("GET", "/annuaire/"): None,
    ("GET", "/annuaire/bureau/"): None,
    ("GET", "/annuaire/bureau/index.html"): None,
    ("GET", "/annuaire/bureau/{page}.html"): None,
    ("GET", "/annuaire/competitions.html"): None,
    ("GET", "/annuaire/index.html"): None,
    ("GET", "/api/admin/access/history"): Role.ADMIN,
    ("GET", "/api/admin/access/roles"): Role.ADMIN,
    ("POST", "/api/admin/access/roles"): Role.ADMIN,
    ("DELETE", "/api/admin/access/roles/{email}"): Role.ADMIN,
    ("PATCH", "/api/admin/access/roles/{email}"): Role.ADMIN,
    ("POST", "/api/admin/access/roles/{email}/invitation"): Role.ADMIN,
    ("POST", "/api/attestations/preview"): Role.ADMIN,
    ("POST", "/api/attestations/send"): Role.ADMIN,
    ("GET", "/api/auth/google/callback"): None,
    ("POST", "/api/auth/google/login"): Role.ADMIN,
    ("GET", "/api/auth/google/status"): Role.COACH,
    ("POST", "/api/auth/google/test"): Role.COACH,
    ("POST", "/api/auth/google/update-token"): Role.ADMIN,
    ("GET", "/api/cloud-db/status"): Role.COACH,
    ("POST", "/api/cloud-db/sync"): Role.ADMIN,
    ("GET", "/api/coaches"): Role.READONLY,
    ("POST", "/api/coaches"): Role.COACH,
    ("DELETE", "/api/coaches/{coach_id}"): Role.COACH,
    ("PUT", "/api/coaches/{coach_id}"): Role.COACH,
    ("GET", "/api/competition-members"): Role.READONLY,
    ("GET", "/api/competitions"): Role.READONLY,
    ("POST", "/api/competitions"): Role.COACH,
    ("POST", "/api/competitions/archive-past"): Role.COACH,
    ("POST", "/api/competitions/cron/fetch-results"): Role.ADMIN,
    ("GET", "/api/competitions/lookup-ffme/{id_ffme}"): Role.READONLY,
    ("DELETE", "/api/competitions/{competition_id}"): Role.COACH,
    ("PATCH", "/api/competitions/{competition_id}"): Role.COACH,
    ("GET", "/api/competitions/{competition_id}/export-excel"): Role.READONLY,
    ("GET", "/api/competitions/{competition_id}/export-pdf"): Role.READONLY,
    ("POST", "/api/competitions/{competition_id}/fetch-results"): Role.COACH,
    ("POST", "/api/competitions/{competition_id}/load-group"): Role.COACH,
    ("POST", "/api/competitions/{competition_id}/participants"): Role.COACH,
    ("DELETE", "/api/competitions/{competition_id}/participants/{adherent_id}"): Role.COACH,
    ("PATCH", "/api/competitions/{competition_id}/participants/{adherent_id}"): Role.COACH,
    ("POST", "/api/competitions/{competition_id}/participants/{adherent_id}/cancel"): Role.COACH,
    ("POST", "/api/competitions/{competition_id}/participants/{adherent_id}/manual-payment"): Role.COACH,
    ("GET", "/api/email-status"): Role.COACH,
    ("GET", "/api/email-templates"): Role.COACH,
    ("POST", "/api/email-templates"): Role.ADMIN,
    ("DELETE", "/api/email-templates/{template_name}"): Role.ADMIN,
    ("GET", "/api/ffme/export"): Role.COACH,
    ("POST", "/api/ffme/import"): Role.ADMIN,
    ("POST", "/api/ffme/preview"): Role.ADMIN,
    ("GET", "/api/ffme/stats"): Role.COACH,
    ("GET", "/api/keys"): Role.COACH,
    ("POST", "/api/keys"): Role.ADMIN,
    ("POST", "/api/keys/{key_id}/assignments"): Role.ADMIN,
    ("POST", "/api/keys/{key_id}/return"): Role.ADMIN,
    ("PATCH", "/api/keys/{key_id}"): Role.ADMIN,
    ("GET", "/api/keys/{key_id}/history"): Role.COACH,
    ("PATCH", "/api/key-assignments/{assignment_id}"): Role.ADMIN,
    ("DELETE", "/api/key-assignments/{assignment_id}"): Role.ADMIN,
    ("GET", "/api/helloasso/campaigns"): Role.COACH,
    ("PUT", "/api/helloasso/campaigns/{kind}"): Role.ADMIN,
    ("GET", "/api/helloasso/items"): Role.COACH,
    ("PUT", "/api/helloasso/items/{id_item}/ignore"): Role.COACH,
    ("PUT", "/api/helloasso/items/{id_item}/link"): Role.COACH,
    ("POST", "/api/helloasso/memberships/import"): Role.ADMIN,
    ("GET", "/api/helloasso/memberships/last-sync"): Role.ADMIN,
    ("POST", "/api/helloasso/memberships/preview"): Role.ADMIN,
    ("POST", "/api/helloasso/sync"): Role.COACH,
    ("GET", "/api/me"): Role.COACH,
    ("GET", "/api/members"): Role.COACH,
    ("POST", "/api/members/add"): Role.ADMIN,
    ("GET", "/api/members/competitors"): Role.COACH,
    ("POST", "/api/members/create"): Role.ADMIN,
    ("POST", "/api/members/update"): Role.ADMIN,
    ("GET", "/api/planning"): Role.COACH,
    ("GET", "/api/planning/export"): Role.COACH,
    ("POST", "/api/planning/item"): Role.COACH,
    ("DELETE", "/api/planning/item/{item_id}"): Role.COACH,
    ("GET", "/api/presence/config"): Role.COACH,
    ("POST", "/api/presence/export"): Role.COACH,
    ("GET", "/api/reports/map-points"): Role.COACH,
    ("GET", "/api/reports/pivot-records"): Role.COACH,
    ("GET", "/api/season-tarifs"): Role.COACH,
    ("GET", "/api/seasons"): Role.COACH,
    ("POST", "/api/send-email"): Role.COACH,
    ("GET", "/api/settings/competitions-results"): Role.COACH,
    ("POST", "/api/settings/competitions-results"): Role.ADMIN,
    ("GET", "/api/web-version"): None,
    ("GET", "/api/whatsapp-template"): Role.COACH,
    ("POST", "/api/whatsapp-template"): Role.ADMIN,
    ("GET", "/bureau"): None,
    ("GET", "/bureau/"): None,
    ("GET", "/bureau/adherents-fiche"): None,
    ("GET", "/bureau/competitions-gestion"): None,
    ("GET", "/bureau/{page}"): None,
    ("GET", "/bureau/{page}/{sub_page}"): None,
    ("GET", "/competitions"): None,
    ("GET", "/competitions/bilan"): None,
    ("GET", "/competitions/coachs"): None,
    ("GET", "/competitions/gestion"): None,
    ("GET", "/competitions/helloasso"): None,
    ("GET", "/docs"): Role.COACH,
    ("GET", "/docs/oauth2-redirect"): Role.COACH,
    ("GET", "/health"): None,
    ("GET", "/index"): None,
    ("GET", "/manifest.webmanifest"): None,
    ("GET", "/openapi.json"): Role.COACH,
    ("GET", "/redoc"): Role.COACH,
    ("GET", "/runtime-config.js"): None,
    ("MOUNT", "/spa"): None,
    ("GET", "/sw.js"): None,
    ("GET", "/webhooks/helloasso"): None,
    ("POST", "/webhooks/helloasso"): None,
}

# Public but deliberately without a route: the browser's automatic request gets a 404, not a 401
PUBLIC_WITHOUT_ROUTE = {"/favicon.ico"}


def _walk(routes: Iterable[BaseRoute]) -> Iterator[tuple[str, str]]:
    """(method, path) of the routes, including those of the included routers. The routers carry
    their own prefix and are included without one, so their route paths are already complete."""
    for route in routes:
        included = getattr(route, "original_router", None)  # recent FastAPI: routers are not flattened
        if included is not None:
            yield from _walk(included.routes)
        elif isinstance(route, Mount):
            yield ("MOUNT", route.path)
        elif isinstance(route, Route):
            yield from ((method, route.path) for method in route.methods or () if method != "HEAD")


def test_route_inventory_unchanged() -> None:
    actual = set(_walk(server.app.routes))
    expected = set(EXPECTED_ROUTES)
    assert sorted(actual - expected) == [], "new routes: add them to EXPECTED_ROUTES, with their role"
    assert sorted(expected - actual) == [], "routes missing or renamed"


def test_every_route_requires_its_expected_role() -> None:
    wrong = {}
    for (method, path), expected_role in EXPECTED_ROUTES.items():
        if method == "MOUNT":
            continue
        actual_role = required_role(method, re.sub(r"\{[^}]+\}", "1", path))
        if actual_role != expected_role:
            wrong[(method, path)] = (expected_role, actual_role)
    assert wrong == {}, "(expected, actual) role of each route that changed"


def test_public_paths_have_a_route() -> None:
    paths = {path for _, path in _walk(server.app.routes)}
    assert sorted(PUBLIC_PATHS - PUBLIC_WITHOUT_ROUTE - paths) == []
