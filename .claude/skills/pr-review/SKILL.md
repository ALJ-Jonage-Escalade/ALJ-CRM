---
name: pr-review
description: Review the current branch against main for code quality (shared utils reused, meaningful names, project rules), apply small fixes, ask the user before complex changes. Use when asked to review the branch or a PR before merging.
---

# PR review

Quality review of the current branch vs `main`. Fix small things yourself; ask before anything bigger.

## 1. Scope (keep context small)
- `git log --oneline main..HEAD` and `git diff main...HEAD --stat`
- Read the diff without generated files:
  `git diff main...HEAD -- . ':!code_source/frontend/openapi.json' ':!code_source/frontend/src/lib/api-schema.ts'`
- Read code around a hunk only where you need it (utils, callers). Don't read whole files.

## 2. Check
- **Utils reused, not rebuilt:** `normalize_string` / `normalize_name` (`domain/utils.py`), `CODE_ROOT` / `ROOT_DIR` / `data_root()` / `template_path()`
  (`src/paths.py`), `domain/members/view.py` helpers, `schema_v2` scores, the repositories of `infrastructure/sqlite/`,
  `AppSettingsRepository`, `api.responses.error()`. In the frontend: `src/services/`, `src/lib/` (`text.ts`…),
  and the types from `api-schema.ts` instead of hand-written ones. Grep before you flag something as duplicated.
- **Names:** say what the value holds; one-letter names only in one-line callbacks and short loops (AGENTS.md § Rules).
- **Rules from AGENTS.md:** `response_model` + regenerated contract, explicit role on new routes, routes in
  `src/api/<theme>/`, `alj` logger (no new `print`), type annotations, no bare `except`, no `Any` / `type: ignore`
  without a reason, `APP_VERSION` == `VERSION` bumped, no secrets or personal data.
- **Simplicity:** dead code, needless copies or conversions, repeated computations, comments that disagree with the code.
- **Risks:** offline path (see memory), loops or repeated work in background ticks, production data and rollout.

## 3. Act
- **Small and local** (renames, reusing a util, typing, a clearer comment): apply it directly.
- **Complex** (behaviour change, several modules, data/rollout, design trade-off): don't edit; ask with
  AskUserQuestion, one question per issue, recommended option first.
- After the edits, run only what's relevant, from `code_source/`: `uv run ruff check src tests && uv run mypy`, pytest on
  the touched test folders, `uv run python dev/export_openapi.py --check` if the API changed, and the frontend
  lint/typecheck/test if `frontend/` changed. Don't commit.

## 4. Report (short)
- What you fixed (file:line, one line each)
- What was already fine (one line)
- Open questions and things you didn't check (e.g. e2e)
