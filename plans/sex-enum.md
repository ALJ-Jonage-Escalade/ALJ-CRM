# Plan — `gender: str` → `sex: Sex | None`

Replace the free-text `gender` field of members with a typed FFME sex, parsed once at the input boundary, and remove
the string guessing spread across the backend and the frontend (`detectGender` in `CompetitionCharts.vue`).

## Decisions (grilling session, 2026-10-28)

| # | Decision |
|---|---|
| D1 | The field is the **FFME administrative sex** (what HelloAsso's "Sexe" collects, what the FFME export and competition categories use). Gender identity, if the club ever needs it, will be a separate optional `gender` field — never extra values in this one |
| D2 | `class Sex(StrEnum): FEMALE = "F"; MALE = "H"` (FFME codes). Missing = `None`, never an enum member. Display labels live only in one frontend mapping |
| D3 | One `parse_sex(raw: object) -> Sex \| None` in `domain/`: lenient on external input (HelloAsso, Excel, legacy data), unparseable → `None` + `logger.warning` with the `order_ref` (no personal data). The API is strict: `Sex \| None`, anything else is a 422 |
| D4 | FFME export: new member (no licence) with `sex is None` → excluded and listed in `ignored_members`, like an invalid birth date (no more silent `"H"`); renewal → `""` |
| D5 | Rename `gender` → `sex` everywhere: Firestore field, SQLite column, domain, API, TS types |
| D6 | Single release: Firestore export → deploy → one-shot migration (backfill `sex`, delete `gender`). Rollback after the migration means restoring the export. The code keeps a read fallback on `gender` (covers the deploy → migration gap) |
| D7 | Single source of truth `crm_users.sex`: competition participants no longer copy it; the competition view reads it from the member doc (member docs persist across seasons). The `categorie_ffme` guess goes |
| D8 | Out of scope: the MyCompet scraper (`infrastructure/mycompet/scraper.py`), which parses the sex of a race category, not of a member — later, separately |

## Phase 1 — Domain: `Sex` and `parse_sex`

- New module `src/domain/members/sex.py` (`from __future__ import annotations`, fully typed, added to `[tool.mypy] files`):
  - `Sex(StrEnum)` with `FEMALE = "F"`, `MALE = "H"`
  - `parse_sex(raw: object) -> Sex | None`: trims, lowercases, strips accents (`normalize_string` from `domain/utils.py`);
    accepts `f`, `femme`, `feminin(e)`, `dame(s)`, `fille` → `F`; `h`, `m`, `homme`, `masculin`, `garcon`, `monsieur/messieurs` → `H`;
    `""`/`None` → `None`; anything else → `None` (the caller logs, `parse_sex` stays pure). Idempotent: `parse_sex("F") == Sex.FEMALE`
- Delete the three copies of `normalize_gender` (`domain/members/models.py:4`, `domain/members/view.py:31`,
  `infrastructure/sqlite/schema_v2.py:212`) and update their callers (`api/reports/pivot.py:74`, `schema_v2.py:331,347`)
- Tests `tests/domain/members/test_sex.py`: parametrized accepted spellings, unknown values, `None`/`""`, idempotence

## Phase 2 — Model, cache and imports

- `Member` (`domain/members/models.py`): `sex: Sex | None = None`; `from_dict` reads `parse_sex(pick("sex", "gender", "champ_Sexe"))`
  and logs a warning (with `order_ref`) when a non-empty raw value does not parse; `to_dict` writes `sex` (`.value` or `None`), no more `gender`
  - `champ_Sexe` stays the Excel / HelloAsso input key (`CORRECTIVE_MAP` in `domain/constants.py:73`); check that the reverse mapping (`models.py:192`) writes the code
- SQLite (`infrastructure/sqlite/schema_v2.py`): column `gender` → `sex` in `users`; field map `champ_Sexe` → `sex`;
  remove the `CASE` of the compat view (`schema_v2.py:663`, expose `u.sex` as is). The cache is rebuilt from Firestore,
  so no SQLite data migration — check how the schema handles an existing `gender` column at startup (rebuild or `ALTER TABLE … RENAME COLUMN`)
- Delete the startup harmonization `UPDATE` in `infrastructure/sqlite/connection.py:254-268`
- `infrastructure/sqlite/members.py:87,231,254`: read and write `sex`, the manual insertion goes through `parse_sex`
- `domain/members/view.py:170`: expose `sex`
- Tests: `Member.from_dict` with a legacy `gender`, a `champ_Sexe` label, an unparseable value (warning logged, `None`)

## Phase 3 — Competitions: read from the member

- `infrastructure/firestore/competitions/participants.py:104`: stop copying the sex into the participant map
- Build the competition view's `sex` from the member doc (`adherent_id`) — `firestore/competitions/adherents.py:113,215` already loads them;
  no extra query per participant
- `api/competitions/schemas/views.py:38,78`: `gender: str` → `sex: Sex | None = None`
- Tests: a participant without a stored sex gets the member's; a member corrected later is reflected

## Phase 4 — API contract

- `api/members/schemas.py:44` (`gender: str`) and `:150` (`Literal["Homme", "Femme", ""]`) → `sex: Sex | None`
- `api/reports/schemas.py:40`: `sex: Sex | None = Field(serialization_alias="Sexe")`; the pivot no longer substitutes `"Inconnu"` (`pivot.py:74`), the frontend labels `null`
- Regenerate: `uv run python dev/export_openapi.py`, then `npm run gen:api` in `frontend/`; commit `openapi.json` and `src/lib/api-schema.ts`
- Tests: a write with `"Femme"` or `"X"` → 422; `null` accepted; `tests/test_route_inventory.py` unchanged (no new route)

## Phase 5 — FFME export

- `exports/membership_excel.py:455-462`: column = `sex.value if sex else ""` (read through `parse_sex` if the export receives raw dicts);
  new member (no licence) with no sex → `continue` + `ignored_members.append("⚠️ [IGNORÉ] {nom} {prenom} (Commande …) : sexe non renseigné")`
- Golden master `tests/exports/test_ffme_golden_master.py` must stay byte-identical: check whether its fixture has a new member
  without sex. If yes, the output changes → the club approves the new reference before merging
- Test: new member without sex is ignored and reported; renewal without sex exports `""`

## Phase 6 — Frontend

- One label mapping, e.g. `src/lib/sex.ts`: `SEX_LABELS: Record<Sex, string>` (`F` → "Femme", `H` → "Homme") + `sexLabel(sex: Sex | null)` → "Non renseigné" for `null`;
  plural forms for the charts if needed. Unit test next to it
- `pages/competitions/detail/CompetitionCharts.vue`: delete `detectGender` (and its `categorie_ffme` guess); count by `row.sex`;
  `GENDER_COLORS` keyed by `Sex` + `null`
- Rename and relabel in: `adherents/MemberForm.vue` (select: `F`/`H`/empty, labels from the mapping), `adherents/members.ts`,
  `adherents/record.ts`, `competitions/competitions.ts`, `outils/PivotPane.vue`, `outils/pivotLayout.ts`, and their tests/fixtures
  (`members.fixture.ts`, `competitions.test.ts`, `PivotPane.test.ts`, `pivotLayout.test.ts`)
- Offline: IndexedDB snapshots saved before the deploy still hold `gender`; the new code shows "Non renseigné" until the next online fetch.
  Accepted (display only; the outbox only queues participant flags, never sex). Check e2e `test_offline.py` still passes
- `npm run format && npm run lint && npm run typecheck && npm test`

## Phase 7 — Migration script

- `scripts/migrate_gender_to_sex.py` (kept in the repo, it runs against production): dry-run by default, `--apply` to write, re-runnable
  - `crm_users`: for each doc with `gender`, set `sex = parse_sex(gender)` (or `None`) and delete `gender` (`firestore.DELETE_FIELD`), in batches
  - competition participant docs: delete the copied `gender`
  - report: counts per resulting value, list of `order_ref`s whose value did not parse (to fix by hand) — no names in the output
  - refuses to run against the emulator unless asked, and against production without `--apply` confirmation
- Test against the emulator with seed data (`dev/seed/seed_emulator.py` updated to write `sex`)

## Phase 8 — Release

- Bump `APP_VERSION` (`src/domain/constants.py`) and `code_source/VERSION`
- All checks: `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`,
  `uv run python dev/export_openapi.py --check`, frontend checks, e2e
- Production rollout (ask before each step):
  1. Firestore export (backup) — the only way back after step 4
  2. `./scripts/deploy_cloud_run.sh --test` and check on the test URL (reads through the `gender` fallback; no writes on member sex there)
  3. `./scripts/deploy_cloud_run.sh` (100 %)
  4. `migrate_gender_to_sex.py` dry-run, review the report, then `--apply`
  5. Fix the reported unparseable members by hand in the app
- Optional later: remove the `gender` read fallback once no doc holds it; a "Sexe non renseigné" filter in the members list
