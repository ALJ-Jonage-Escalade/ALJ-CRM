"""HTML pages: the Vue application (code_source/frontend/, plan_frontend_vue.md) on every page address, the former
addresses redirected to it, and the static web files (web/: service worker, manifest, logo, shared scripts)."""

from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from paths import CODE_ROOT

router = APIRouter()

WEB_DIR = os.path.join(CODE_ROOT, "web")

# Office pages of the Vue application (frontend/src/router.ts): its entry page answers them. The pages are public,
# the data stays behind the API (ID token, roles).
_SPA_PAGES = frozenset({"adherents", "communications", "competitions", "outils", "parametres", "planning"})
# Former addresses of the competitions management pages (phone and office, until plan phase 11): now the competitions
# screen itself, where coaches change everything
FORMER_MANAGEMENT_PAGES = {"/competitions/gestion": "/competitions", "/bureau/competitions-gestion": "/bureau/competitions"}


# Vue application, built by `npm run build` (frontend/dist) or by the Dockerfile. Its hashed assets
# are served under /spa/ (Vite `base`); its entry page answers the routes already migrated.
SPA_ASSETS_PATH = "/spa"


def frontend_dist() -> str:
    """Build output of the Vue application (ALJ_FRONTEND_DIST overrides it, for the tests)."""
    return os.environ.get("ALJ_FRONTEND_DIST") or os.path.join(CODE_ROOT, "frontend", "dist")


class _BuildFiles(StaticFiles):
    """Static files of a build that may not exist yet (frontend not built): 404 instead of an error."""

    async def check_config(self) -> None:
        if self.directory is not None and os.path.isdir(self.directory):
            await super().check_config()


def spa_entry() -> Response:
    """Entry page of the Vue application; never cached by the browser (it names the current assets)."""
    p = os.path.join(frontend_dist(), "index.html")
    if os.path.exists(p):
        return FileResponse(p, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return HTMLResponse("<h1>Interface web non compilée</h1>"
                        "<p>Lancer <code>npm run build</code> dans <code>code_source/frontend/</code>.</p>", status_code=503)


def mount_static(app: FastAPI) -> None:
    """Static web files: a router cannot carry mounts, so they are added to the app itself."""
    # Static web files (logo, competitions page…) also served under /annuaire/ (the directory itself: /index).
    if os.path.isdir(WEB_DIR):
        app.mount("/annuaire", StaticFiles(directory=WEB_DIR, html=True), name="annuaire")

    # Ressources communes du portail bureau (CSS, modules JavaScript) : web/shared/.
    shared_dir = os.path.join(WEB_DIR, "shared")
    if os.path.isdir(shared_dir):
        app.mount("/static-web", StaticFiles(directory=shared_dir), name="static-web")

    app.mount(SPA_ASSETS_PATH, _BuildFiles(directory=frontend_dist(), check_dir=False), name="spa")


@router.get("/bureau", response_class=HTMLResponse, include_in_schema=False)
@router.get("/bureau/", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_home():
    """Accueil du portail bureau : application Vue."""
    return spa_entry()

@router.get("/bureau/adherents-fiche", include_in_schema=False)
def get_former_member_record(request: Request) -> RedirectResponse:
    """Member record of the former members page (2.14): now in the Vue app, same query (?id=…&saison=…, ?ajout=1)."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/bureau/adherents{query}", status_code=302)

@router.get("/bureau/competitions-gestion", include_in_schema=False)
@router.get("/competitions/gestion", include_in_schema=False)
def get_former_management_page(request: Request) -> RedirectResponse:
    """Former competitions management pages (bookmarks, installed shortcuts): the competitions screen, same query."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=FORMER_MANAGEMENT_PAGES[request.url.path] + query, status_code=302)

@router.get("/bureau/{page}", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_page(page: str) -> Response:
    """Office pages: the Vue application (_SPA_PAGES), else 404."""
    if page in _SPA_PAGES:
        return spa_entry()
    return HTMLResponse("<h1>Page bureau introuvable</h1>", status_code=404)

@router.get("/index", response_class=HTMLResponse)
def get_annuaire_page() -> Response:
    """Directory of the members (read only, readable offline): Vue application, on phones as on desktop."""
    return spa_entry()

@router.get("/annuaire/", include_in_schema=False)
@router.get("/annuaire/index.html", include_in_schema=False)
def get_former_annuaire_page(request: Request) -> RedirectResponse:
    """Former address of the directory page (web/index.html under the /annuaire/ mount): now /index."""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(url=f"/index{query}", status_code=302)


@router.get("/")
def root_route() -> RedirectResponse:
    """Point d'entrée racine : les compétitions (application Vue)."""
    return RedirectResponse(url="/competitions", status_code=302)


@router.get("/competitions", response_class=HTMLResponse)
def get_competitions_page() -> Response:
    """Competitions (readable offline, changed offline through the outbox) and the Google sign-in callback (the OAuth
    redirect URI registered for the club): Vue application, on phones as on desktop. Also the PWA's start page."""
    return spa_entry()
