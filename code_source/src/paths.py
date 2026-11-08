"""Folders of the application: CODE_ROOT (code_source/, /app in the Docker image), ROOT_DIR (its parent: the
repository locally) and DATA_ROOT (SQLite cache and local data, ALJ_DATA_DIR overrides it)."""

from __future__ import annotations

import os

CODE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # this file lives in src/
ROOT_DIR = os.path.dirname(CODE_ROOT)

# Never overwritten by a code update; ALJ_DATA_DIR points it elsewhere (dev, tests)
DATA_ROOT = os.environ.get("ALJ_DATA_DIR") or os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_ROOT, exist_ok=True)


def find_doc_template(filename: str) -> str:
    """Path of a template of doc/template (resources of the code, copied into the Docker image)."""
    return os.path.join(CODE_ROOT, "doc", "template", filename)
