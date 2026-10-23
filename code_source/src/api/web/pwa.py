"""PWA shell files: manifest, service worker (built with the Vue application), browser runtime configuration, app
version."""

from __future__ import annotations

import json
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from api.web.pages import WEB_DIR, frontend_dist
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
def get_sw() -> Response:
    """Service worker of the Vue application (frontend/src/sw.ts, hashed precache), built into frontend/dist. Served
    from / for its scope to cover every page; same address as the former hand-written worker, which it replaces in
    the browsers that have it. Checked again on every visit (no-cache)."""
    p = os.path.join(frontend_dist(), "sw.js")
    if os.path.exists(p):
        return FileResponse(p, media_type="application/javascript", headers={"Cache-Control": "no-cache"})
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


class AppVersion(BaseModel):
    app_version: str


@router.get("/api/web-version", response_model=AppVersion)
def get_web_version() -> AppVersion:
    """Version deployed (code_source/VERSION, APP_VERSION): the app compares it with its own to offer an update. Never
    cached by the service worker."""
    return AppVersion(app_version=APP_VERSION)
