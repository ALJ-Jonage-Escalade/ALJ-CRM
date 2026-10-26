import os
import sys
from typing import List

# S'assurer que le dossier src est dans sys.path (exécution directe, docker ou package)
_src_dir = os.path.dirname(os.path.abspath(__file__))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from fastapi import FastAPI

from dotenv import load_dotenv
load_dotenv()

# Imported for its side effect before the check below: loads the .env files (ROOT_DIR/.env overrides)
import infrastructure.security.secret_store  # noqa: F401
from infrastructure import runtime_env

# Inconsistent dev mode (Firebase emulator) or dev mode on Cloud Run: stop immediately.
runtime_env.validate()


app = FastAPI(title="Admin Escalade API")

# Access control (Firebase token + firestore.rules roles): enforced on Cloud Run and in the
# Docker image (ALJ_API_AUTH=required), off for the desktop app's local server, which is
# protected by local_guard_middleware instead (loopback hosts, same-origin writes).
import re
from fastapi.routing import APIRoute
from infrastructure.firestore.cloud_database import CloudDatabase
from starlette.concurrency import run_in_threadpool


# Paths of the routes that only read/write Firestore collections (competitions, coaches,
# projections, HelloAsso mirror) through CompetitionFirestoreRepository: they never touch the
# SQLite cache, so they must not wait for its refresh (a full rebuild after a cold start).
# Filled from their routers once included (below). Exact routes, not path prefixes: other routes
# under /api/competitions (results batch, check-all-paid) use the cache.
FIRESTORE_ONLY_PATHS: List[re.Pattern[str]] = []


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
        await run_in_threadpool(CloudDatabase.after_write)
    return response


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
from api.auth import me
from api.communications import attestations, email, whatsapp
from api.members import dashboard, members, seasons
from api.ffme import ffme
from api.integrations import cloud_db, google_auth, helloasso
from api.reports import map as members_map, pivot
from api.web import health, pages, pwa
from api.responses import service_error_handler
from services.errors import ServiceError
for _api in (competitions, participants, coaches, competition_members, helloasso_items,
             results, payments, members, seasons, dashboard, email, whatsapp, attestations,
             planning, presence, members_map, pivot, ffme,
             helloasso, google_auth, cloud_db, me,
             pages, pwa, health):
    app.include_router(_api.router)
pages.mount_static(app)
# Every route of these routers skips the SQLite cache refresh: a route that reads or writes the
# cache (members, app settings, HelloAsso payments…) must live in another router, even under
# /api/competitions (results batch, check-all-paid). /api/me reads no data at all.
FIRESTORE_ONLY_PATHS.extend(r.path_regex for _api in (competitions, participants, coaches, competition_members, helloasso_items, me)
                            for r in _api.router.routes if isinstance(r, APIRoute))
app.add_exception_handler(ServiceError, service_error_handler)

# No CORS: every page calls the API from its own origin. Allowing other origins would let any
# website read the local (unauthenticated) desktop server.

if __name__ == "__main__":
    import uvicorn
    # Support de la variable d'environnement PORT (Cloud Run injecte PORT=8080)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")  # noqa: S104 - Cloud Run (PORT set) needs all interfaces
    uvicorn.run("server:app", host=host, port=port, reload=(port == 8000))
