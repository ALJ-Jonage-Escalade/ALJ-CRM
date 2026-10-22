"""HTML pages: competitions and directory PWAs, desk portal (bureau), static web files.

The portal is moving to a Vue application (code_source/frontend/, plan_frontend_vue.md) one page at a
time: migrated pages answer with its entry page, the others still serve their file from web/."""

from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from domain.constants import APP_VERSION
from paths import CODE_ROOT

router = APIRouter()

WEB_DIR = os.path.join(CODE_ROOT, "web")
COMPETITIONS_PAGE_PATH = os.path.join(WEB_DIR, "competitions.html")
_annuaire_page_path = os.path.join(WEB_DIR, "index.html")

# Portail « bureau » (ordinateur) : pages publiques, les données restent protégées
# (lecture Firestore avec le compte Google, appels API avec jeton).
_bureau_dir = os.path.join(WEB_DIR, "bureau")
_BUREAU_PAGES = {
    "adherents": "adherents.html",
    "competitions": "competitions.html",
    "planning": "planning.html",
    "outils": "outils.html",
}
# Pages migrated to the Vue application (frontend/src/router.ts): its entry page answers them
_SPA_PAGES = frozenset({"communications", "parametres"})


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
    # Fichiers web statiques (annuaire, logo...) également servis sous /annuaire/.
    # L'annuaire lit la base des adhérents dans Firestore (connexion Google du coach).
    if os.path.isdir(WEB_DIR):
        app.mount("/annuaire", StaticFiles(directory=WEB_DIR, html=True), name="annuaire")

    # Ressources communes du portail bureau (CSS, modules JavaScript) : web/shared/.
    shared_dir = os.path.join(WEB_DIR, "shared")
    if os.path.isdir(shared_dir):
        app.mount("/static-web", StaticFiles(directory=shared_dir), name="static-web")

    app.mount(SPA_ASSETS_PATH, _BuildFiles(directory=frontend_dist(), check_dir=False), name="spa")


def _bureau_file(page: str):
    name = _BUREAU_PAGES.get(page)
    p = os.path.join(_bureau_dir, name) if name else ""
    if p and os.path.exists(p):
        return FileResponse(p, media_type="text/html")
    return HTMLResponse("<h1>Page bureau introuvable</h1>", status_code=404)

@router.get("/bureau", response_class=HTMLResponse, include_in_schema=False)
@router.get("/bureau/", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_home():
    """Accueil du portail bureau : application Vue."""
    return spa_entry()

@router.get("/bureau/{page}", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_page(page: str):
    """Pages du portail bureau : application Vue (_SPA_PAGES) ou ancienne page (_BUREAU_PAGES), sinon 404."""
    if page in _SPA_PAGES:
        return spa_entry()
    return _bureau_file(page)

@router.get("/index", response_class=HTMLResponse)
def get_annuaire_page():
    """Annuaire des adhérents (lecture seule) : lit la base principale dans
    Firestore (collections crm_*) avec le compte Google du coach."""
    if os.path.exists(_annuaire_page_path):
        return FileResponse(_annuaire_page_path, media_type="text/html")
    return HTMLResponse("<h1>Page web/index.html introuvable</h1>", status_code=404)


@router.get("/")
def root_route():
    """Point d'entrée racine : redirige vers la PWA Mobile des compétitions."""
    if os.path.exists(COMPETITIONS_PAGE_PATH):
        return RedirectResponse(url="/competitions", status_code=302)
    return {
        "service": "ALJ Escalade Cloud API",
        "version": APP_VERSION,
        "docs_url": "/docs",
        "health_url": "/health",
        "competitions_url": "/competitions",
        "annuaire_url": "/index"
    }


@router.get("/competitions", response_class=HTMLResponse)
def get_competitions_page():
    """Page web de gestion des compétitions : données en temps réel depuis
    Google Cloud Firestore (même base que l'application de bureau)."""
    if os.path.exists(COMPETITIONS_PAGE_PATH):
        return FileResponse(COMPETITIONS_PAGE_PATH, media_type="text/html")
    return HTMLResponse("<h1>Page web/competitions.html introuvable</h1>", status_code=404)
