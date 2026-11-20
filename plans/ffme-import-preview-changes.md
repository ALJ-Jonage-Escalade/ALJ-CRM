# FFME import: preview of every change before writing

## Problem
Outils › Import FFME › « Analyser & Prévisualiser le fichier » only shows counts (rows read, matched by licence /
by name) and the unmatched rows. Nothing says which members will change, nor how: the office applies the import
blind. Two rows of the file can also hit the same member (the last one silently wins), and a licensee with no
active registration on the season goes unnoticed.

## Decisions (grilling of 2026-11-19)
- Q1 — The table lists only the matched rows that change something; members recognised with nothing to change are
  only counted (« N adhérents reconnus sans changement »). Rows with a warning (Q4, Q7) are listed even unchanged.
- Q2 — One row per matched file row: member (name, birth date), « Rapproché par » badge (licence / nom / manuel),
  one column per field (licence, passeports, diplômes, document de santé, statut) showing `ancien → nouveau` when
  it changes, empty otherwise; long values truncated, full value in a tooltip.
- Q3 — Manual links are diffed by the server too: `/api/ffme/preview` accepts `manual_matches`; each dropdown pick
  calls the preview again (stale answers ignored) and the table is redrawn, the row badged « Manuel ».
- Q4 — A matched member with no active (not cancelled / refunded) registration on the season is always listed,
  status cell « ⚠️ Aucune inscription active sur la saison », with a counter.
- Q5 — « ⚡ Importer & Fusionner directement » is removed: the only path is Analyser → check → Appliquer.
- Q6 — A checkbox per automatic row, ticked by default; unticked rows stay visible, greyed, and are not written
  (`excluded_rows`). Manual links are left out with « Ignorer », as today.
- Q7 — A member targeted by several ticked rows (automatic or manual) is flagged « ⚠️ Adhérent rapproché par
  plusieurs lignes du fichier »; Appliquer is disabled until resolved, and `/api/ffme/import` refuses it (400).
- Q8 — Sorted by what needs attention, then alphabetically: blocked (Q7), no active registration (Q4), manual,
  by name, by licence. No group filters; one search field (name or licence, accents and case ignored) filtering
  both the changes table and the unmatched list.
- Defaults: the unmatched list stays its own section; the season is the active one, shown in the title.

## Changed while building
- Every row has the checkbox, manual ones included (the server applies `excluded_rows` to all rows): one rule.
- The pane keeps the unmatched rows of the first analysis (the server drops linked rows from `unmatched`), so a
  linked row keeps its picker and the link can be undone; changes and counters come from the latest preview.
- Only `unchanged_count` and `season` are new counters on the server; « à modifier » (ticked rows that change
  something), « sans inscription active » and the blocked members are derived in the browser from `changes`.
- `FfmeRowChange.licence`: the member's licence after the import, so that the search finds a row whose licence
  does not change.
- Added after a review note: `FfmeRowChange.licence_conflict` names another member already holding the file's
  licence (a sibling's number typed on HelloAsso, the row now sent to the right child by the birth date). Listed and
  ranked with « sans inscription active », warning « ⚠️ Licence N déjà enregistrée sur X : à corriger sur sa fiche »;
  never cleared automatically, the stored number may be the right one.
- Health document (production values: QS, COMPETITION, LOISIR — valid, the member may climb — or ATTENTE): an empty
  cell of the « Document de santé » column is read as ATTENTE (a file without the column keeps the stored values).
  The preview cell shows ✅ for a valid new value, ❌ for ATTENTE, then the value; old → new in the tooltip.
- Test file: `dev/seed/seed_emulator.py` writes `dev/seed/ffme_licencies_dev.xlsx` (git-ignored, `dev/seed/ffme_cases.py`),
  one row per case of the preview, from the seed data.
- Several purchases of a season only coexist at equal priority (the member writers drop the lower ones), so the
  planner marks every active one; old status shown as their distinct statuses.

## Design
### Rows are identified by their Excel line
Every licensee row carries `row_number` (its line in the sheet). A manual match becomes `{row_number, user_id}`:
the server reads the row's values from the file itself (the client no longer copies licence / passports /
diplomas / health document back). Exclusions are `excluded_rows: List[int]`. Two rows hitting the same member stay
two rows.

### One planner, shared by the preview and the import
The preview and the import must not disagree, so the import writes the values the preview computed:
- `domain/members/ffme_changes.py` (pure): from a matched row (file values) and the member's current state (licence,
  passports, diplomas, season purchases), computes the final values and the list of `FieldChange(field, old, new)`:
  - licence, passports, diplomas, health document: an empty file value keeps the stored one;
  - status « Terminé » and health document go to every purchase of the season not cancelled / refunded
    (`is_cancelled`); old status shown as the distinct statuses of those purchases (`Validé`, `Validé / En cours`);
  - no such purchase → `no_active_registration`, user fields still change.
- `infrastructure/sqlite/ffme_import.py`:
  - `list_members_for_matching` also returns `raw_passports`, `raw_diplomas`;
  - new `list_season_purchases(season) -> Dict[user_id, List[{id, status, document_sante}]]` (one query);
  - `apply_ffme_matches` writes final values (no more `COALESCE` in SQL): users by id, purchases by id.
- `services/members/ffme.py`:
  - `prepare_licensees(excel, manual_matches)` → rows (automatic + manual) with their changes, duplicates flagged,
    unmatched rows (minus those linked by hand), counters;
  - `apply_import(season, excel, manual_matches, excluded_rows)`: same planning, drops excluded rows, raises
    `InvalidRequest` on a member targeted twice, writes the rows that change something; returns that count
    (« N adhérents mis à jour » no longer counts no-op rows).

### API (`api/ffme/schemas.py`)
- `FfmePreviewRequest(FfmeFile)`: `manual_matches: List[FfmeManualMatch]` (`row_number`, `user_id`).
- `FfmeImportRequest(FfmePreviewRequest)`: `season`, `excluded_rows`.
- `FfmePreview` adds `season`, `changes: List[FfmeRowChange]`, `unchanged_count`; `FfmeLicensee` adds `row_number`.
- `FfmeRowChange`: `row_number`, `user_id`, `last_name`, `first_name`, `birth_date`, `licence`, `source`
  (`licence` | `nom` | `manuel`), `changes: List[FfmeFieldChange(field, old, new)]`, `no_active_registration`,
  `duplicate`.
- Regenerate `frontend/openapi.json` and `src/lib/api-schema.ts`.

### Frontend (`pages/outils/ffme/`)
- `ffme.ts` (pure, Vitest): `sortChanges`, `matchesSearch(row, query)`, `blockedUserIds(changes, excluded, manual)`,
  `manualMatches` → `{row_number, user_id}`, confirmation text counting ticked rows.
- `FfmeChangesTable.vue`: the table (checkbox, badge, `ancien → nouveau` cells, tooltips, warnings).
- `FfmeImportPane.vue`: counter tiles (to change, unchanged, without active registration, unmatched), search field,
  re-preview on each pick, Appliquer disabled while blocked, quick import removed.

## Steps (TDD, one vertical slice each)
1. Planner: field rules (empty keeps, cancelled skipped, no active registration) — domain tests.
2. Preview returns the changes of automatic rows; only changing / warning rows; counters — service + route tests.
3. Import writes the planned values; returns the count of changed rows — repository / service tests (replace the
   `COALESCE` tests).
4. Manual matches by `row_number`, in the preview and the import.
5. Duplicates flagged in the preview, refused by the import; `excluded_rows` honoured.
6. API contract regenerated; frontend helpers (sort, search, blocked) — Vitest.
7. Frontend table, search, re-preview, quick import removed — `OutilsPage.test.ts`, e2e `test_outils.py` updated.
8. Version bump, docs (page text), all checks.
