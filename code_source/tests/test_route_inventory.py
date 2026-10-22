"""Route inventory of the app: moving routes between modules must not add, drop or rename any URL.

External callers depend on these exact paths: Cloud Scheduler (`batch-resultats-competitions`,
POST /api/competitions/cron/fetch-results every day at 07:00), the HelloAsso webhook, the Google
OAuth redirect URIs, the deploy health check and the installed PWAs.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from starlette.routing import BaseRoute, Mount, Route

import server
from infrastructure.security.api_auth import PUBLIC_PATHS

# (method, path) of every route; "MOUNT" for the static file mounts. HEAD is left out
# (Starlette adds it to every GET).
EXPECTED_ROUTES = {
    ("GET", "/"),
    ("MOUNT", "/annuaire"),
    ("POST", "/api/attestations/preview"),
    ("POST", "/api/attestations/send"),
    ("GET", "/api/auth/google/callback"),
    ("GET", "/api/auth/google/login"),
    ("GET", "/api/auth/google/status"),
    ("POST", "/api/auth/google/test"),
    ("POST", "/api/auth/google/update-token"),
    ("GET", "/api/cloud-db/status"),
    ("POST", "/api/cloud-db/sync"),
    ("GET", "/api/coaches"),
    ("POST", "/api/coaches"),
    ("DELETE", "/api/coaches/{coach_id}"),
    ("PUT", "/api/coaches/{coach_id}"),
    ("GET", "/api/competition-members"),
    ("GET", "/api/competitions"),
    ("POST", "/api/competitions"),
    ("POST", "/api/competitions/archive-past"),
    ("POST", "/api/competitions/cron/fetch-results"),
    ("POST", "/api/competitions/{comp_id}/check-all-paid"),
    ("POST", "/api/competitions/{comp_id}/fetch-results"),
    ("DELETE", "/api/competitions/{competition_id}"),
    ("PATCH", "/api/competitions/{competition_id}"),
    ("POST", "/api/competitions/{competition_id}/load-group"),
    ("POST", "/api/competitions/{competition_id}/participants"),
    ("DELETE", "/api/competitions/{competition_id}/participants/{adherent_id}"),
    ("PATCH", "/api/competitions/{competition_id}/participants/{adherent_id}"),
    ("POST", "/api/competitions/{competition_id}/participants/{adherent_id}/cancel"),
    ("POST", "/api/competitions/{competition_id}/participants/{adherent_id}/manual-payment"),
    ("GET", "/api/dashboard"),
    ("GET", "/api/email-status"),
    ("GET", "/api/email-templates"),
    ("POST", "/api/email-templates"),
    ("DELETE", "/api/email-templates/{template_name}"),
    ("GET", "/api/ffme/export"),
    ("POST", "/api/ffme/import"),
    ("POST", "/api/ffme/preview"),
    ("GET", "/api/ffme/stats"),
    ("GET", "/api/helloasso/items"),
    ("PUT", "/api/helloasso/items/{id_item}/ignore"),
    ("PUT", "/api/helloasso/items/{id_item}/link"),
    ("POST", "/api/helloasso/sync"),
    ("GET", "/api/me"),
    ("GET", "/api/members"),
    ("POST", "/api/members/add"),
    ("GET", "/api/members/competitors"),
    ("POST", "/api/members/create"),
    ("POST", "/api/members/update"),
    ("GET", "/api/planning"),
    ("POST", "/api/planning"),
    ("GET", "/api/planning/export"),
    ("POST", "/api/planning/item"),
    ("DELETE", "/api/planning/item/{item_id}"),
    ("GET", "/api/presence/config"),
    ("POST", "/api/presence/export"),
    ("POST", "/api/preview-email"),
    ("GET", "/api/season-tarifs"),
    ("GET", "/api/seasons"),
    ("POST", "/api/send-email"),
    ("GET", "/api/settings/competitions-results"),
    ("POST", "/api/settings/competitions-results"),
    ("GET", "/api/web-version"),
    ("GET", "/api/whatsapp-template"),
    ("POST", "/api/whatsapp-template"),
    ("GET", "/bureau"),
    ("GET", "/bureau/"),
    ("GET", "/bureau/adherents-fiche"),
    ("GET", "/bureau/{page}"),
    ("GET", "/competitions"),
    ("GET", "/docs"),
    ("GET", "/docs/oauth2-redirect"),
    ("GET", "/health"),
    ("GET", "/index"),
    ("GET", "/manifest.webmanifest"),
    ("GET", "/map"),
    ("GET", "/openapi.json"),
    ("GET", "/pivot"),
    ("GET", "/redoc"),
    ("GET", "/runtime-config.js"),
    ("MOUNT", "/static-web"),
    ("MOUNT", "/spa"),
    ("GET", "/sw.js"),
    ("GET", "/webhooks/helloasso"),
    ("POST", "/webhooks/helloasso"),
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
    assert sorted(actual - EXPECTED_ROUTES) == [], "new routes: add them to EXPECTED_ROUTES"
    assert sorted(EXPECTED_ROUTES - actual) == [], "routes missing or renamed"


def test_public_paths_have_a_route() -> None:
    paths = {path for _, path in _walk(server.app.routes)}
    assert sorted(PUBLIC_PATHS - PUBLIC_WITHOUT_ROUTE - paths) == []
