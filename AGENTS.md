# AGENTS.md — ALJ-CRM

Membership management for the climbing section of the Amicale Laïque de Jonage: a Windows desktop client (PySide6)
and a web app (FastAPI + PWA) on Google Cloud Run, with data in Firestore.
User docs: `README.md` · Architecture: `ARCHITECTURE.md` · Local dev stack: `code_source/dev/README.md`.
Python conventions (lint, typing, tests): `code_source/AGENTS.md`.

## Setup
See @./README.md

## Local dev (emulator only, no production access)
```bash
docker compose -f dev/docker-compose.yml up -d    # Firebase emulator (:4000) + Mailpit (:8025)
set -a && source dev/dev.env && set +a
uv run python dev/seed/seed_emulator.py           # (re)seed fake data
uv run dev/run_server.sh                          # FastAPI with reload → http://localhost:8080/bureau/
docker compose -f dev/docker-compose.yml down     # stop (emulator data kept in dev/.emulator-data/)
```
- Health: http://localhost:8080/health · API docs: http://localhost:8080/docs
- Sign in through the emulator account picker (e.g. `albus.dumbledore@alj-escalade.fr` = admin)
- HelloAsso endpoints call the real API and fail without credentials — expected in dev

## Checks (same as CI)
- all: `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`
- unit tests without Qt: `uv run pytest tests --ignore=tests/presentation`
- Qt tests: `QT_QPA_PLATFORM=offscreen uv run pytest tests/presentation/<file>.py`, one file per process
- e2e: not managed by uv — `pip install -r requirements-docker.txt -r requirements-e2e.txt`, `python -m playwright install chromium`, then `python -m pytest -c e2e/pytest.ini e2e` (needs Docker; see `dev/README.md`)

## Deployment — production, ask before running
- `./deploy_cloud_run.sh --test` — test revision with 0 % traffic, dedicated URL
- `./deploy_cloud_run.sh` — production (100 % traffic)
- `./deploy_cloud_run.sh --rollback [<REV>]` — switch traffic back (code only, never data)
- `./deploy_cloud_run.sh --cleanup` — remove the test URL
- Firestore rules are deployed separately: `firebase deploy --only firestore:rules` (applies to production immediately)
- The test revision uses **production data and secrets**: actions there (e-mails, member edits) are real

## Rules
- Never commit or print secrets: `code_source/.env` holds HelloAsso, Google OAuth and SMTP credentials
- Never commit personal data (databases, exports, `tests/fixtures/`): members' health, emergency contacts, minors (GDPR)
- Never point dev tools at production: dev mode only works against the `demo-alj` emulator project
- Put throwaway diagnostic scripts (`check_*`, `query_*`, ad-hoc queries) in `scripts_temporaires/` at the repo root (git-ignored), never in `code_source/`
- Versioning: bump `APP_VERSION` in `src/domain/constants.py` and `code_source/VERSION` together on every functional change (release CI checks tag == `VERSION` == `APP_VERSION`; the `pyproject.toml` version is not used)

## Data & domain rules
- Firestore is the source of truth (`crm_<table>` collections); `database.db` is a SQLite cache rebuilt from it (`infrastructure/cloud_database.py`). Write routes must go through `SqliteRepository` so changes are replicated
- FFME CSV export (`exports/membership_excel.generate_ffme_csv`): strict format (`;` separator, `dd/mm/yyyy` dates); `tests/exports/test_ffme_golden_master.py` must stay byte-identical, or the reference is renewed with the club's approval
- HelloAsso `customFields`: the value can be in `answer` or `value` — always read both
- Name matching: use `normalize_string` / `normalize_name` from `domain/utils.py`; never rebuild paths by hand, import `CODE_ROOT` / `ROOT_DIR` / `DATA_ROOT` from `src/paths.py`
- SQLite backups: use the SQLite backup API (`SqliteRepository.create_db_backup`), never a raw file copy (WAL)
- New API routes declare an explicit role (`admin` for any write or e-mail send); Cloud Run is ephemeral → generate files in memory and return them, never persist locally
- Generated Excel sheets (attendance, emergency contacts) follow the club style: Segoe UI, dark blue `1E3A8A` headers, orange `EA580C` for emergency, zebra rows, print gridlines on
