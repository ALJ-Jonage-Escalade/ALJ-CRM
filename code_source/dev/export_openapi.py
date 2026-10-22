"""Writes (or checks) frontend/openapi.json, the API contract of the Vue app, from the FastAPI app.

The Pydantic response models are the source of truth; frontend/src/lib/api-schema.ts is generated from this
file (`npm run gen:api` in frontend/). Both files are versioned and checked by the CI.

    uv run python dev/export_openapi.py            # rewrites frontend/openapi.json
    uv run python dev/export_openapi.py --check    # fails when it is stale (CI)
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # code_source/
TARGET = os.path.join(ROOT, "frontend", "openapi.json")


def spec() -> str:
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from server import app
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str]) -> int:
    expected = spec()
    if "--check" in argv:
        current = ""
        if os.path.exists(TARGET):
            with open(TARGET, "r", encoding="utf-8") as f:
                current = f.read().replace("\r\n", "\n")
        if current != expected:
            print("frontend/openapi.json est périmé par rapport aux modèles de l'API.", file=sys.stderr)
            print("Lancer : uv run python dev/export_openapi.py, puis npm run gen:api dans frontend/", file=sys.stderr)
            return 1
        return 0
    with open(TARGET, "w", encoding="utf-8", newline="\n") as f:
        f.write(expected)
    print("écrit : frontend/openapi.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
