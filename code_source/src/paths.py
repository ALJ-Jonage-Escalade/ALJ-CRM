"""Folders of the application: CODE_ROOT (code_source/, /app in the Docker image), ROOT_DIR (its parent: the
repository locally) and data_root() (SQLite cache and local data, ALJ_DATA_DIR overrides it)."""

from __future__ import annotations

import os

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # this file lives in src/
ROOT_DIR = os.path.dirname(CODE_ROOT)



def data_root() -> str:
    """Folder of the SQLite cache and the local data, created if missing; never overwritten by a code update.
    ALJ_DATA_DIR points it elsewhere (dev, tests): read on each call, so it follows the environment of the moment."""
    folder = os.path.abspath(os.environ.get("ALJ_DATA_DIR") or os.path.join(ROOT_DIR, "data"))
    os.makedirs(folder, exist_ok=True)
    return folder


# Files read at runtime (document templates, images), shipped with the code in src/
ASSETS_DIR = os.path.join(CODE_ROOT, "src", "assets")


def template_path(filename: str) -> str:
    """Path of a document template of src/assets/templates (attestation, attendance sheet)."""
    return os.path.join(ASSETS_DIR, "templates", filename)
