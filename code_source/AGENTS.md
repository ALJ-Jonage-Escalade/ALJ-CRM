# AGENTS.md — Python Project

All commands run from `code_source/`. Python 3.14 (`.python-version`), `requires-python >= 3.11`.

## Commands
- install: `uv sync --group web` (dev group by default, `web` adds WeasyPrint for the attestation PDFs and their tests, which needs Pango, see `README.md`; CI: `uv sync --frozen --group web`)
- test: `uv run pytest tests` — always pass `tests`: bare `uv run pytest` also collects `e2e/` and fails without Playwright
- e2e: not managed by uv — `pip install -r requirements-docker.txt -r requirements-e2e.txt`, `python -m playwright install chromium`, then `python -m pytest -c e2e/pytest.ini e2e` (needs Docker and `npm run build` in `frontend/`; see `dev/README.md`)
- lint: `uv run ruff check src tests`
- typecheck: `uv run mypy` (no path: checks the files listed under `[tool.mypy] files` in pyproject.toml; `mypy src/` fails on module-path errors)
- all checks (as CI): `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`
- API contract: `uv run python dev/export_openapi.py --check` (`frontend/openapi.json` matches the Pydantic models)
- frontend (Vue 3 + Vite + TypeScript, in `frontend/`, Node version from `frontend/.nvmrc`):
  `cd frontend && npm ci && npm run check:api && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`
  - API types: `src/lib/api-schema.ts` is generated from `openapi.json` (`uv run python dev/export_openapi.py`, then
    `npm run gen:api`); never edit either by hand. Pages call the API through the typed client (`src/lib/client.ts`)
  - dev: `npm run dev` → http://localhost:5173/bureau/, next to `uv run dev/run_server.sh` (Vite proxies the API, `/map`, `/pivot` and the PWA files)
  - lint: official Vue preset (`@vue/eslint-config-typescript`, type-aware rules) in `eslint.config.js`; format: Prettier
    (`.prettierrc.json`, width 140), enforced in CI — run `npm run format` before committing
  - unit tests: Vitest, `src/**/*.test.ts` next to the module they test

## Critical Rules
1. Use `uv run <cmd>` for all commands — never activate venv manually
2. Add dependencies with `uv add <pkg>` (`--group web|dev` as needed), not pip install, then run `uv run python dev/export_requirements.py` to regenerate the versioned `requirements*.txt`
3. Type-annotate new and modified functions and methods
4. Use pytest to run tests
5. Log through the `alj` logger (`logging.getLogger("alj")`); `print()` remains in older server code (stdout goes to Cloud Logging); do not add new ones
6. Handle errors explicitly — no bare `except: pass`

## Code Style
- Linter: ruff (not flake8); rule set and ignores in `[tool.ruff.lint]`
- Formatting: `ruff format` is not enforced yet (most files are unformatted) — do not run `ruff format .` on the whole tree; it creates huge unrelated diffs
- Line length: 140 characters (pyproject.toml)
- Import sorting: ruff handles this (not isort)
- Use f-strings, not .format() or %
- Prefer a TypedDict to returning `dict[str, Any]`

## Type Checking
- mypy is being adopted progressively: only the files listed in `[tool.mypy] files` are checked (not strict, `check_untyped_defs = false`)
- When a file is fully typed, add it to that `files` list
- No `Any` without a comment explaining why
- No `type: ignore` without a specific error code and reason
- `from __future__ import annotations` in new source files

## Testing
- Framework: pytest runner; existing tests are mostly `unittest.TestCase` classes, which pytest runs natively — follow the style of the file you are editing; plain pytest functions are fine for new files
- Location: `tests/` mirroring the `src/` structure (`tests/domain/`, `tests/infrastructure/`, …)
- Naming: test_<module>.py / test_<function>_<scenario>()
- Shared fixtures: `conftest.py` (`tests/conftest.py` strips dev env variables and forces production mode)
- Use pytest.mark.parametrize (or `subTest` in TestCase classes) for multiple input cases
- Per-test timeout: 120 s (`pytest.ini`)
