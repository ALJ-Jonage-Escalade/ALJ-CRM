"""HTML pages: competitions and directory PWAs, desk portal (bureau), static web files."""

from __future__ import annotations

import os

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    "": "index.html",
    "adherents": "adherents.html",
    "communications": "communications.html",
    "competitions": "competitions.html",
    "planning": "planning.html",
    "outils": "outils.html",
    "parametres": "parametres.html"
}


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


def _bureau_file(page: str):
    name = _BUREAU_PAGES.get(page)
    p = os.path.join(_bureau_dir, name) if name else ""
    if p and os.path.exists(p):
        return FileResponse(p, media_type="text/html")
    return HTMLResponse("<h1>Page bureau introuvable</h1>", status_code=404)

@router.get("/bureau", response_class=HTMLResponse, include_in_schema=False)
@router.get("/bureau/", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_home():
    """Accueil du portail bureau (ordinateur)."""
    return _bureau_file("")

@router.get("/bureau/{page}", response_class=HTMLResponse, include_in_schema=False)
def get_bureau_page(page: str):
    """Pages du portail bureau : seules les pages de _BUREAU_PAGES sont servies."""
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
