import logging
import os
import sys
from typing import List

# S'assurer que le dossier src est dans sys.path (exécution directe, docker ou package)
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from dotenv import load_dotenv
load_dotenv()

# Imported for its side effect before the check below: loads the .env files (ROOT_DIR/.env overrides)
import infrastructure.security.secret_store  # noqa: F401
from infrastructure import runtime_env

# Inconsistent dev mode (Firebase emulator) or dev mode on Cloud Run: stop immediately.
runtime_env.validate()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: the bootstrap admin (BOOTSTRAP_ADMIN_EMAIL) joins the access list if absent; never blocks startup."""
    from infrastructure.security import role_directory
    from services.access.bootstrap import run_at_startup
    await run_in_threadpool(run_at_startup, role_directory.current())
    yield


app = FastAPI(title="Admin Escalade API", lifespan=lifespan)

# Access control (Firebase token + roles of the access list): enforced on Cloud Run and in the
# Docker image (ALJ_API_AUTH=required), off for a local dev or test server (ALJ_API_AUTH=off), which is
# protected by local_guard_middleware instead (loopback hosts, same-origin writes).
import re
from fastapi.routing import APIRoute
from infrastructure.firestore.cloud_database import CloudDatabase


# Paths of the routes that only read/write Firestore collections (competitions, coaches,
# projections, HelloAsso mirror) through CompetitionFirestoreRepository: they never touch the
# SQLite cache, so they must not wait for its refresh (a full rebuild after a cold start).
# Filled from their routers once included (below). Exact routes, not path prefixes: other routes
# under /api/competitions (check-all-paid) use the cache.
FIRESTORE_ONLY_PATHS: List[re.Pattern[str]] = []

# Set on a write's answer when it was saved in the SQLite cache but could not be sent to Firestore yet
REPLICATION_PENDING_HEADER = "X-Replication-Pending"
logger = logging.getLogger("alj")


def uses_sqlite_cache(path: str) -> bool:
    """True for the data routes served from the SQLite cache of the crm_* collections."""
    if any(p.match(path) for p in FIRESTORE_ONLY_PATHS):
        return False
    return path.startswith("/api/")


async def cloud_db_middleware(request, call_next):
    """Base principale dans Firestore : le cache SQLite du serveur est mis à jour
    avant les routes de données, et les écritures sont envoyées juste après.
    Enregistré avant le contrôle d'accès : il ne s'exécute qu'après lui."""
    relevant = uses_sqlite_cache(request.url.path)
    # Cloud Run, or local dev on the emulator: the cache follows Firestore as in production
    server_mode = os.environ.get("K_SERVICE") or runtime_env.is_dev()
    if relevant and server_mode and CloudDatabase.is_enabled():
        await run_in_threadpool(CloudDatabase.ensure_fresh, 30)
    response = await call_next(request)
    if relevant and request.method not in ("GET", "HEAD", "OPTIONS") and CloudDatabase.is_enabled():
        if not await run_in_threadpool(CloudDatabase.after_write):
            # Saved in the server's cache but not in Firestore yet (retried by the next sync). Not an error status:
            # the write did happen, and a retried send-email or member creation would be done twice
            logger.error("[CLOUD_DB] %s %s: write kept pending, Firestore replication failed", request.method, request.url.path)
            response.headers[REPLICATION_PENDING_HEADER] = "1"
    return response


from api.responses import unhandled_error_middleware
app.middleware("http")(unhandled_error_middleware)  # innermost: registered first
app.middleware("http")(cloud_db_middleware)

from infrastructure.security.api_auth import auth_middleware, local_guard_middleware
app.middleware("http")(auth_middleware)
# Unauthenticated local server only accepts loopback hosts and same-origin writes
app.middleware("http")(local_guard_middleware)


async def security_headers_middleware(request, call_next):
    """Baseline browser protections on every response (including errors from the guards)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    # Pages may only be framed by the site itself (clickjacking); srcdoc frames are unaffected
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    return response


app.middleware("http")(security_headers_middleware)  # outermost

# Data routes of the web front end (competitions, coaches, HelloAsso links, members): src/api/
from api.competitions import coaches, competitions, helloasso_items, participants
from api.competitions import members as competition_members
from api.competitions import payments, results
from api.activities import planning, presence
from api.admin import access
from api.auth import me
from api.communications import attestations, email, whatsapp
from api.members import dashboard, helloasso_import, members, seasons
from api.ffme import ffme
from api.integrations import cloud_db, google_auth, helloasso, helloasso_campaigns
from api.reports import map as members_map, pivot
from api.web import health, pages, pwa
from api.responses import service_error_handler
from domain.errors import ServiceError
for _api in (competitions, participants, coaches, competition_members, helloasso_items,
             results, payments, members, seasons, dashboard, helloasso_import, email, whatsapp, attestations,
             planning, presence, members_map, pivot, ffme,
             helloasso, helloasso_campaigns, google_auth, cloud_db, me, access,
             pages, pwa, health):
    app.include_router(_api.router)
pages.mount_static(app)
# Every route of these routers skips the SQLite cache refresh: a route that reads or writes the
# cache (members, email templates, HelloAsso payments…) must live in another router, even under
# /api/competitions (check-all-paid). /api/me and /api/admin/access only use the access list,
# /api/helloasso/campaigns the app_settings collection and HelloAsso. The MyCompet results batch
# (results) reads its settings from Firestore: Cloud Scheduler's 07:00 call must not wait for a
# full cache rebuild on a cold start (180 s deadline).
FIRESTORE_ONLY_PATHS.extend(r.path_regex for _api in (competitions, participants, coaches, competition_members, helloasso_items,
                                                      results, me, access, helloasso_campaigns)
                            for r in _api.router.routes if isinstance(r, APIRoute))
app.add_exception_handler(ServiceError, service_error_handler)

# No CORS: every page calls the API from its own origin. Allowing other origins would let any
# website read a local (unauthenticated) dev server.

if __name__ == "__main__":
    import uvicorn
    # Support de la variable d'environnement PORT (Cloud Run injecte PORT=8080)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")  # noqa: S104 - Cloud Run (PORT set) needs all interfaces
    uvicorn.run("server:app", host=host, port=port, reload=(port == 8000))
