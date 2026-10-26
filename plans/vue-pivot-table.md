# Plan: pivot table (TCD) of the Outils page in the Vue app

> Follows decision D10 of `documentations/plan_frontend_vue.md` (« the pivot stays an iframe ») and the map migration
> (#25, `pages/outils/MembersMap.vue` + `/api/reports/map-points`), which is the pattern to copy.

## Why

`/pivot` (`src/api/reports/pivot.py`) builds a whole HTML page in Python, injects the members as JSON in a `<script>`,
and loads jQuery 3.6, jQuery UI 1.12.1 (known CVEs) and PivotTable.js 2.23 from cdnjs. The Vue app fetches it with the
token and shows it in a sandboxed `srcdoc` iframe. The bureau wants an Excel-like « tableau croisé dynamique »; the
PivotTable.js UI is fine, the way it is built is not.

## Decisions (grilled 2026-10-25)

1. **Library: `vue-pivottable` 1.4.1** (native Vue 3 port of PivotTable.js, MIT, typed; only dependency
   `vue-draggable-next` → `sortablejs`, MIT, touch drag; no `innerHTML` / `v-html` / `eval` in the bundle). Same UI
   as today: drag and drop of the fields between unused / rows / cols, value filter per field, aggregator, renderer,
   sort per axis, totals.
2. **Data shaping stays in Python.** The loop of `get_pivot_table` becomes a pure typed function
   `pivot_records(season) -> List[PivotRecord]` (status normalisation, `clean_city_name`, `normalize_gender`, age at
   season start and age bands, ISO date and month, Déjà membre / Nouvelle inscription), served by
   `GET /api/reports/pivot-records?season=` with a Pydantic `response_model`:
   - `PivotRecords { season: str, records: List[PivotRecord] }`, `season` = the season actually read (as `MapPoints`)
   - `PivotRecord`: the 12 fields with **the French labels as JSON keys** through Pydantic `alias`
     (« Nom », « Groupe / Tarif », « Tranche d'Âge »…): vue-pivottable shows the attribute names as is; `Âge: int | None`
   - season resolution through `resolve_season` of `map.py` (moved somewhere shared if needed, not duplicated)
   - errors: `internal_error` / `error(500)` as `map.py`, instead of today's `except Exception → "[]"` (silently empty table)
   - role: coach (default, fail-closed), as `/pivot` today; under `/api/` so the SQLite cache refresh applies
3. **Layout persistence** (`localStorage`, key `alj.pivot.layout.v1`, per browser — the layout holds no personal data):
   - saved: `rows`, `cols`, `vals`, `aggregatorName`, `rendererName`, `rowOrder`, `colOrder`, on `update:pivotModel`
     (debounced)
   - **not saved: `valueFilter`**; it is reset to the defaults on each visit and **on each season change** (tariff
     names change from season to season), while the rest of the layout is kept across season changes and 🔄 Recharger
   - read through a pure `restoreLayout(raw, attributes, aggregators, renderers)`: unknown fields dropped, unknown
     aggregator / renderer → default, broken JSON or `localStorage` unavailable → defaults, silently
   - « ↺ Disposition par défaut » button: clears the key and restores the defaults
   - defaults (today's): rows `Groupe / Tarif`; cols `Statut`, `Sexe`; exclusions `Groupe / Tarif: Liste d'attente cours`,
     `Statut: Annulé`; Effectif; Tableau
4. **Own French `aggregators` and `renderers` props** (the package's `fr` locale is broken: key `frAggregators`, and it
   lacks the fractions), built from `PivotUtilities.aggregatorTemplates` and the exported renderers:
   - aggregators: **Effectif** (default) · % du total · % de la ligne · % de la colonne · Valeurs distinctes ·
     Âge moyen · Âge min · Âge max; `hiddenFromAggregators` = every field but `Âge`
   - renderers: **Tableau** (default) · Carte de chaleur · Carte de chaleur par ligne · Carte de chaleur par colonne ·
     Export (copier vers Excel) (the TSV renderer)
   - locale strings: the package's French ones (`selectAll`, `filterResults`, `totals`…)
5. **Look**: package CSS + a small override scoped under `.alj-pivot`, porting today's rules (`pvtTable` th/td,
   dropdowns, `pvtVals`) to the app's Tailwind tokens. Old blue header dropped (the Outils card has the title); its
   hint (« Glissez et déposez les étiquettes… ») kept above the table. **Phones: ignored** (wide table,
   `overflow-x-auto`, no dedicated layout). Check in e2e that the filter popups are not clipped by the scroll wrapper;
   if they are, only the output cell scrolls.
6. **Loading**: `vue-pivottable` and its CSS loaded with `defineAsyncComponent` on first opening of the tab (not with
   the map). Loading / error / offline states as `MembersMap` (`errorText`). `reload()` exposed for 🔄 Recharger.
7. **Small choices**: `Âge` `None` → « Inconnu » in the frontend service (filterable; skipped by the age
   aggregators, not a number). « Toutes les saisons »: a member of several seasons counts once per season (`Saison`
   is a field). No custom `sorters` (natural sort orders the age bands and ISO months).
8. **Clean removal in the same PR, no transition**: a tab left open across the deploy gets « HTTP 404 » on the pivot
   until reloaded, as for `/map` in #25.

## Done 2026-10-26 (2.23.0)

Deviations from the decisions above, found while building:
- **Age aggregators bound to `Âge`** (no field dropdown) instead of `hiddenFromAggregators`: hiding the other fields
  would also have hidden them from « Valeurs distinctes », which keeps a free choice of field.
- **Layout saved at once**, not debounced: the table already groups the events of a drag, and a page reloaded within
  the debounce lost the last change (caught by e2e). After « ↺ Disposition par défaut » the table sends the default
  layout back, so the stored value is the default rather than empty (same effect).
- **vue-pivottable 1.4.1 bugs worked around in `pivotLayout.ts` / `PivotPane.vue`**: the `fr` locale names its
  aggregators `frAggregators` (own list passed); the table reads the « Totaux » label from the whole language pack
  (the renderer wrappers pass the locale strings); `showRowTotal` / `showColTotal` default to `false` through Vue's
  boolean casting (passed explicitly).
- **Age of each row at the start of its own season** (« Toutes les saisons » used to age everyone at the current
  year's season start).
- No scroll wrapper issue: the filter popups are drawn on top (e2e `test_pivot_table_by_season` checks it).
- `resolve_season` moved to `api/reports/__init__.py`, shared by the map and the pivot table.
- Not updated (dated records): `documentations/plan_audit_issues.md`, `documentations/plan_pages_web_bureau.md`.

## Work

### Backend
- [x] `api/reports/schemas.py`: `PivotRecord` (aliases), `PivotRecords`
- [x] `api/reports/pivot.py`: `pivot_records(season)` + `GET /api/reports/pivot-records` (`response_model`,
      `error_responses(500)`); delete the HTML route `/pivot`
- [x] `domain/utils.py`: delete `json_for_script` (only used by `/pivot`) and its tests
- [x] `server.py`: `uses_sqlite_cache` loses `or path == "/pivot"`
- [x] Add the file to `[tool.mypy] files` once fully typed
- [x] `uv run python dev/export_openapi.py` then `npm run gen:api`; commit `openapi.json` and `api-schema.ts`

### Frontend
- [x] `npm install --save-exact vue-pivottable@1.4.1` (check the resolved `vue-draggable-next` / `sortablejs` licenses)
- [x] `services/reports.ts`: `pivotRecords(season)` (`Âge` `null` → « Inconnu »)
- [x] `pages/outils/pivotLayout.ts` (pure): defaults, aggregators, renderers, `restoreLayout`, save / clear
- [x] `pages/outils/PivotPane.vue`: async vue-pivottable, `season` prop, `v-model:pivotModel`, filter reset on season
      change, « ↺ Disposition par défaut », `.alj-pivot` styles, `reload()`
- [x] `OutilsPage.vue`: `PivotPane` instead of `ToolFrame`; update its header comment
- [x] Delete `pages/outils/ToolFrame.vue`; `sw.ts` comment (no `/pivot`)

### Tests
- [x] pytest `pivot_records`: status mapping (Processed / Terminé / Traité → Validé, cancelled, refused, other),
      city merge, gender, age and every band boundary (9/10, 17/18, 24/25, 29/30, 39/40, 49/50, 64/65, unknown),
      bad / missing dates, Déjà membre, « active » and « Toutes les saisons »; the route answers 500 through
      `internal_error` on failure (replaces `tests/web/test_bureau_web.py::test_pivot_table_configuration_and_fields`)
- [x] `tests/test_route_inventory.py`: `/api/reports/pivot-records` in, `/pivot` out
- [x] `tests/test_api_foundations.py`, `tests/infrastructure/security/test_api_security.py`: drop `/pivot` and the
      leftover `/map`; add `/api/reports/pivot-records`
- [x] `tests/test_untrusted_output.py`: drop `TestJsonForScript`, `TestServerPagesEscapeMemberData`,
      `TestToolsIframesIsolated`
- [x] Vitest `pivotLayout.test.ts`: `restoreLayout` (unknown field / aggregator / renderer, broken JSON, storage
      throwing), `valueFilter` never stored
- [x] Vitest `PivotPane`: a record whose `Nom` is `<img src=x onerror=…>` renders as text, no `<img>` created
      (replaces the iframe isolation check); layout kept and filters reset on season change; default-layout button
- [x] Vitest `OutilsPage.test.ts`: iframe cases replaced (`GET /api/reports/pivot-records`, error HTTP 500, offline)
- [x] e2e `test_pivot_table_by_season`: rewritten for the component (season switch, a filter popup opens and is not
      clipped, layout kept after reload); drop `_HARNESS_ERRORS` in `e2e/conftest.py` (sandboxed iframe gone)

### Docs and version
- [x] `documentations/plan_frontend_vue.md` D10: pivot done (no more iframe, jQuery UI gone)
- [x] `ARCHITECTURE.md`, `desktop_features_missing_in_web.md`, `guide_deploiement_cloud_run_helloasso.md`,
      `plan_pages_web_bureau.md`: `/pivot` → `/api/reports/pivot-records`, leftover `/map` mentions cleaned
- [x] `plans/vue-responsive-frontend.md`: note under phase 6 / « Served by FastAPI » that `/map` and `/pivot` are gone
- [x] Bump `APP_VERSION` (`src/domain/constants.py`) and `VERSION`

### Checks
- [x] Python: `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`
- [x] Frontend: `npm audit --omit=dev --audit-level=high && npm run check:api && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`
- [x] Semgrep (repo root) and e2e Outils
