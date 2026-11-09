"""Ratchet on the mypy errors of the whole src/ tree (CI).

`uv run mypy` checks the files listed in pyproject.toml only; this runs mypy on every file of src/ and fails when
the error count goes above MAX_ERRORS. Fix errors, then lower MAX_ERRORS to the new count.

    uv run python dev/mypy_ratchet.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

MAX_ERRORS = 41
CODE_ROOT = Path(__file__).resolve().parent.parent  # code_source/


def main() -> int:
    files = sorted(str(path.relative_to(CODE_ROOT)) for path in (CODE_ROOT / "src").rglob("*.py"))
    result = subprocess.run([sys.executable, "-m", "mypy", *files], cwd=CODE_ROOT, capture_output=True, text=True,  # noqa: S603 - fixed arguments
                            env={**os.environ, "PYTHONWARNINGS": "ignore"}, check=False)
    found = re.search(r"Found (\d+) errors?", result.stdout)
    count = int(found.group(1)) if found else 0
    if count > MAX_ERRORS:
        print(result.stdout)
        print(f"mypy over src/: {count} errors, more than the ratchet ({MAX_ERRORS}). Fix the new ones.")
        return 1
    note = f" Lower MAX_ERRORS in {Path(__file__).name} to {count}." if count < MAX_ERRORS else ""
    print(f"mypy over src/: {count} errors (ratchet {MAX_ERRORS}).{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
