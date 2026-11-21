# Plan: statistics page with charts (members + competitions), TCD removed

> Source: grilling session of 2026-11-21 (no issue). Branch: `feat/stats_improvements`. At least one commit per phase,
> built test-first (red → green → refactor).

## Architectural decisions

Durable decisions that apply across all phases:

- **Library**: Chart.js 4 (MIT, community-run, D5), `npm install --save-exact chart.js`, only the pie/doughnut/bar
  controllers registered (tree-shaken). No `vue-chartjs`: a small owned wrapper `components/ui/UiChart.vue`.
  Every chart renders a visually hidden `<table>` with the same figures (screen readers; tests, jsdom draws no canvas).
- **Endpoint**: `GET /api/reports/member-stats` (role coach, as `pivot-records` today), router `api/reports/`,
  every season in one answer. Row: `user_id, sex, age, age_band, city, group, status, season, returning, order_month`,
  English keys, **no names, no full order date** (data minimisation). Status grouped server-side (`status_label`:
  Validé / Annulé / Refusé / raw). Route inventory updated, OpenAPI + `api-schema.ts` regenerated.
- **Counting** (pure `pages/outils/stats/memberStats.ts`, unit-tested):
  - members = **one person per season**, status **Validé** only; a person counts in every group they paid for
    (group totals may exceed the member total: the chart says so);
  - cancelled registrations = **purchases** with status Annulé in the season (Refusé not counted);
  - unknown sex / city / age are their own grey category, never hidden; the average age skips unknown ages.
- **Member section** (season picker on top, `SeasonSelect` without « Toutes les saisons », active season by default;
  the season change filters locally, no request):
  - cards: total members, % women, % new members, average age, cancelled registrations;
  - charts (click → inline stacked bars, count / % toggle):
    | Chart | Type | Breakdown |
    |---|---|---|
    | Sexe | pie | sex per group |
    | Nouveaux / renouvellements | pie | per group |
    | Tranches d'âge | bars (age order) | sex per age band |
    | Groupes | horizontal bars, largest first | sex per group |
    | Villes | horizontal bars, top 10 + « Autres » | sex per city (top 10) |
    | Inscriptions par mois | bars | new/returning per month |
  - « Adhérents par saison »: bars stacked by sex, every season, independent of the picker, no breakdown.
- **Drill-down**: the breakdown of the whole chart, inline under the card; opened by a click on the chart or by the
  « Détail › » button (keyboard/touch); no highlighted slice. Mobile layout: later.
- **Competition section**: same figures and `stats.ts`, last 3 seasons, no drill-down; 3 cards unchanged; podiums →
  bars stacked gold/silver/bronze; competitors per season → bars.
- **Online only**: one request through `createReportsApi(...).memberStats()` (no polling: the figures do not need to
  follow live edits; the page's reload button reloads), nothing kept on the device; offline → « Statistiques
  indisponibles hors ligne » instead of empty charts.
- **Colours**: fixed per category from `components/ui/palette.ts` (F, H, non renseigné, medals), same on every chart.
- **TCD removed**: `OutilsPivotPage.vue`, `pages/outils/pivot/`, sub-page `pivot` (router, `lib/access.ts`, Outils
  menu), `vue-pivottable`, `/api/reports/pivot-records` and their tests (unit, web, e2e); docs mentioning the TCD.
- `APP_VERSION` and `code_source/VERSION` bumped together.

---

## Phase 1: endpoint + gender pie (tracer bullet)

**User stories**: a coach opens Outils › Statistiques and sees the gender pie of the active season.

### What to build
`/api/reports/member-stats` (schema, service from the SQLite cache, route inventory, OpenAPI regenerated), the
`reports` service method, `memberStats.ts` with the season filter + per-person dedup + sex count, Chart.js + `UiChart`,
and a member section with the season picker and the gender pie, online only.

### Acceptance criteria
- [ ] Endpoint returns every season's rows without names; coach role in the inventory
- [ ] A person with two validated purchases in a season counts once; Annulé/Refusé excluded
- [ ] The pie's hidden table lists F / H / Non renseigné with counts
- [ ] Offline: the « indisponibles hors ligne » message, no chart

---

## Phase 2: every member chart, cards and drill-down

### What to build
The other charts and cards of the member section, the « Adhérents par saison » chart, the inline drill-down
(click or « Détail › », count / % toggle).

### Acceptance criteria
- [ ] Cards: total, % women, % new, average age (unknown ages skipped), cancelled purchases
- [ ] Cities: top 10 + « Autres »; groups: note when totals exceed the members
- [ ] « Détail › » toggles the stacked breakdown; % mode sums to 100 per bar
- [ ] Season change re-filters without a request

---

## Phase 3: competition section on Chart.js

### Acceptance criteria
- [ ] Same figures as before (existing `stats.ts` tests still pass); podiums stacked by medal, competitors as bars

---

## Phase 4: remove the TCD

### Acceptance criteria
- [ ] No `pivot` sub-page, route, menu entry, component, test or `vue-pivottable` left; `/api/reports/pivot-records` gone
- [ ] Docs updated (ARCHITECTURE, desktop_features_missing_in_web, …); version bumped
- [ ] All checks green: Python (`ruff`, `mypy`, `pytest tests`, `export_openapi --check`) and frontend (lint, format,
      typecheck, tests, build)
