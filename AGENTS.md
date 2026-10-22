# AGENTS.md — ALJ-CRM

Membership management for the climbing section of the Amicale Laïque de Jonage: a web app (FastAPI + PWA) on
Google Cloud Run, with data in Firestore. (The former Windows desktop client was removed; see
`documentations/desktop_features_missing_in_web.md`.)
User docs: `README.md` · Architecture: `documentations/ARCHITECTURE.md` · Local dev stack: `code_source/dev/README.md`.
Python conventions (lint, typing, tests): `code_source/AGENTS.md`.
Frontend: being migrated page by page to a Vue 3 app in `code_source/frontend/` (plan: `plans/vue-responsive-frontend.md`,
decisions: `documentations/plan_frontend_vue.md`); pages not migrated yet stay in `code_source/web/`.

## Setup
See @./README.md

## Local dev (emulator only, no production access)
```bash
docker compose -f dev/docker-compose.yml up -d    # Firebase emulator (:4000) + Mailpit (:8025)
set -a && source dev/dev.env && set +a
uv run python dev/seed/seed_emulator.py           # (re)seed fake data
uv run dev/run_server.sh                          # FastAPI with reload (API + pages not migrated)
cd frontend && npm ci && npm run dev              # Vue app, hot reload → http://localhost:5173/bureau/ (proxies the rest to :8080)
docker compose -f dev/docker-compose.yml down     # stop (emulator data kept in dev/.emulator-data/)
```
- Health: http://localhost:8080/health · API docs: http://localhost:8080/docs
- Sign in through the emulator account picker (e.g. `albus.dumbledore@alj-escalade.fr` = admin)
- HelloAsso endpoints call the real API and fail without credentials — expected in dev

## Checks (same as CI)
- all: `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`
- frontend (from `code_source/frontend/`, Node from `.nvmrc`): `npm ci && npm run check:api && npm run lint && npm run typecheck && npm test && npm run build`
- API contract: `uv run python dev/export_openapi.py --check` (`frontend/openapi.json` matches the Pydantic models)
- unit tests: `uv sync --group web && uv run pytest tests` (the `web` group brings WeasyPrint/pydyf, needed by the attestation tests; WeasyPrint needs Pango, see `README.md`)
- e2e: not managed by uv — `pip install -r requirements-docker.txt -r requirements-e2e.txt`, `python -m playwright install chromium`, then `python -m pytest -c e2e/pytest.ini e2e` (needs Docker and the Vue app built: `npm run build` in `frontend/`; see `dev/README.md`)

## Deployment — production, ask before running
Run from `code_source/` (the script always uploads `code_source/`); Windows scripts live in `scripts/` and `code_source/scripts/`
- `./scripts/deploy_cloud_run.sh --test` — test revision with 0 % traffic, dedicated URL
- `./scripts/deploy_cloud_run.sh` — production (100 % traffic)
- `./scripts/deploy_cloud_run.sh --rollback [<REV>]` — switch traffic back (code only, never data)
- `./scripts/deploy_cloud_run.sh --cleanup` — remove the test URL
- Firestore rules are deployed separately: `cd code_source/firestore && firebase deploy --only firestore:rules` (applies to production immediately)
- The test revision uses **production data and secrets**: actions there (e-mails, member edits) are real

## Rules
- Never commit or print secrets: `code_source/.env` holds HelloAsso, Google OAuth and SMTP credentials
- Never commit personal data (databases, exports, `tests/fixtures/`): members' health, emergency contacts, minors (GDPR)
- Never point dev tools at production: dev mode only works against the `demo-alj` emulator project
- Put throwaway diagnostic scripts (`check_*`, `query_*`, ad-hoc queries) in `scripts_temporaires/` at the repo root (git-ignored), never in `code_source/`
- API contract: routes called by the Vue app declare a Pydantic `response_model` (errors: `api.responses.error()` +
  `error_responses()`); after changing one, run `uv run python dev/export_openapi.py` then `npm run gen:api` in
  `frontend/`, and commit `frontend/openapi.json` and `frontend/src/lib/api-schema.ts` (both generated, checked by CI)
- Frontend dependencies: `npm install --save-exact <pkg>` in `code_source/frontend/` (lockfile committed); MIT or equivalent
  licenses only (decision D5); never commit `frontend/dist/` or `node_modules/`
- Versioning: bump `APP_VERSION` in `src/domain/constants.py` and `code_source/VERSION` together on every functional change (`tests/test_cloud_run_lot4.py` checks `VERSION` == `APP_VERSION`; the `pyproject.toml` version is not used)

## Data & domain rules
- Firestore is the source of truth (`crm_<table>` collections); `database.db` is a SQLite cache rebuilt from it (`infrastructure/firestore/cloud_database.py`). Write routes must go through the repositories of `infrastructure/sqlite/` (`MemberRepository`, `PlanningRepository`, …; connection and schema in `SqliteDatabase`) so changes are replicated
- FFME CSV export (`exports/membership_excel.generate_ffme_csv`): strict format (`;` separator, `dd/mm/yyyy` dates); `tests/exports/test_ffme_golden_master.py` must stay byte-identical, or the reference is renewed with the club's approval
- App settings (key/value: HelloAsso campaign, WhatsApp text, results batch e-mail…) live only in the Firestore `app_settings` collection: `infrastructure/firestore/app_settings.AppSettingsRepository`
- HelloAsso `customFields`: the value can be in `answer` or `value` — always read both
- Name matching: use `normalize_string` / `normalize_name` from `domain/utils.py`; never rebuild paths by hand, import `CODE_ROOT` / `ROOT_DIR` / `DATA_ROOT` from `src/paths.py`
- SQLite backups: use the SQLite backup API (`SqliteDatabase.create_db_backup`), never a raw file copy (WAL)
- New API routes go in a router `src/api/<theme>/<domain>.py`, never in `server.py` (app assembly only); add them to `tests/test_route_inventory.py`. A route that touches the SQLite cache must not join the Firestore-only routers listed in `server.py`
- New API routes declare an explicit role (`admin` for any write or e-mail send); Cloud Run is ephemeral → generate files in memory and return them, never persist locally
- Generated Excel sheets (attendance, emergency contacts) follow the club style: Segoe UI, dark blue `1E3A8A` headers, orange `EA580C` for emergency, zebra rows, print gridlines on
