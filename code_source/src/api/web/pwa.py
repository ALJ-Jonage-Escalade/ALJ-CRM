"""PWA shell files: manifest, service worker, browser runtime configuration, web version."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response

from api.web.pages import COMPETITIONS_PAGE_PATH, WEB_DIR
from domain.constants import APP_VERSION
from infrastructure import runtime_env

router = APIRouter()


@router.get("/manifest.webmanifest")
def get_manifest():
    """Manifeste PWA pour installation sur smartphone."""
    p = os.path.join(WEB_DIR, "manifest.webmanifest")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/manifest+json")
    return HTMLResponse("Not found", status_code=404)

@router.get("/sw.js")
def get_sw():
    """Service Worker PWA pour cache hors-ligne."""
    p = os.path.join(WEB_DIR, "sw.js")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/javascript")
    return HTMLResponse("Not found", status_code=404)

@router.get("/runtime-config.js", include_in_schema=False)
def get_runtime_config():
    """Browser runtime configuration (Firebase emulator in dev, nothing in production)."""
    payload = json.dumps(runtime_env.client_config(), ensure_ascii=False)
    return Response(
        content=f"window.ALJ_RUNTIME = Object.freeze({payload});\n",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


def _read_web_version() -> str:
    """Version de la page web (balise <meta name="alj-web-version"> de competitions.html)."""
    import re
    try:
        with open(COMPETITIONS_PAGE_PATH, "r", encoding="utf-8") as f:
            m = re.search(r'<meta name="alj-web-version" content="([^"]+)"', f.read(4000))
        return m.group(1) if m else ""
    except OSError:
        return ""


@router.get("/api/web-version")
def get_web_version():
    """Version en ligne de la page web (jamais mise en cache par le service worker)."""
    return {"web_version": _read_web_version(), "app_version": APP_VERSION}
