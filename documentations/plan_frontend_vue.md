# Plan: Vue 3 single-page frontend

> Written 2026-10-21 from a design review (grilling session) on `main` @ `eec18c1`.
> Status: decisions taken, nothing implemented yet. Open questions are listed at the end.

## Why

`code_source/web/` is about 13k lines of vanilla JS in 9 HTML pages, without a build step:

- Rendering is `innerHTML` + a hand-written `esc()` copied into 9 files; member data comes from the public HelloAsso
  form, so every missed `esc()` is an XSS.
- Phone and desktop are separate pages (`competitions.html` / `bureau/competitions.html`, ~2.7k lines each;
  `index.html` / `bureau/adherents.html`), and `shared/alj-vue.js` redirects by screen width. Only 4 `@media`
  queries exist: nothing is responsive.
- Plumbing is maintained by hand: the service worker precache list, the web version repeated in 9 `<meta>` tags + `sw.js`,
  role e-mail lists mirrored from `api_auth.py`.

Goal: one responsive app (phone and desktop share the same screens), safer by default, nicer to work on.

## Decisions

### D1 — Framework: Vue 3 + Vite, one SPA with `vue-router`
Templates escape by default; one shared layout (sidebar on desktop, bottom tab bar on phones) and shared state
(user, role, offline store). `/bureau/*`, `/competitions` and `/index` become routes of the same app.
Migration is gradual: FastAPI serves the SPA `index.html` for migrated routes and the old HTML for the others.

### D2 — Offline: per route, same scope as today
- Competitions: offline read + outbox (offline `PATCH` replayed when the network comes back), on any device.
- Directory (members read view): offline read only.
- Admin screens (adherents edit, planning, parametres, …): online only — no health/emergency data cached on laptops.
- Same protections: wipe on logout, 401/403, user change, 30-day age limit.
- `alj-store.js` and `alj-sync.js` are kept almost as is, converted to TypeScript modules, and exposed through a
  `useSyncedResource(name, url, { offline })` composable. No rewrite of this edge-case-heavy code.

### D3 — TypeScript, with API types generated from OpenAPI
Only 4 of 76 routes declare a `response_model` today. Each migrated page adds Pydantic response models to the
routes it calls; TS types are generated from `/openapi.json` (`openapi-typescript`) and CI checks they are up to
date (like `requirements*.txt`).

### D4 — Auth: same login flow, roles from the server
- Port the implicit Google OAuth + `signInWithCredential` flow as is into a `useAuth()` composable, with the modular
  `firebase` npm package (replaces the v10 compat SDK from gstatic).
- New `GET /api/me` → `{ email, role }` computed by `api_auth.role_for_claims`. Delete `ADMIN_EMAILS`,
  `COACH_EMAILS`, `READONLY_EMAILS` from the frontend (and the test that mirrors them): volunteers' e-mails are no
  longer published in public JS.
- The OAuth callback stays on `/competitions` (now an SPA route): no change in the Google Cloud console.

### D5 — UI: Reka UI (headless) + Tailwind CSS + TanStack Table, components owned in the repo
Revised 2026-10-22. PrimeVue was first chosen, then dropped: PrimeVue 5 (2026-10) moved to a commercial "PrimeUI"
license with a license key (free Community tier for non-profits, renewed yearly, notice shown when the key is missing
or expired); 4.5.5 is the last MIT release and is frozen. Requirement since then: **MIT (or equivalent) open source,
no single vendor whose license change could force a rewrite**.
- **Reka UI** (MIT): behaviour and accessibility only (dialogs with focus trap, tabs, select, toast, keyboard, ARIA).
- **Tailwind CSS v4** (MIT): styling; responsive layout written with breakpoint prefixes. Club theme as design tokens
  (dark blue `1E3A8A`, orange `EA580C`, Segoe UI).
- **TanStack Table** (MIT): table logic (sort, filters, pagination). One responsive data table component of our own
  (table on desktop, cards on phones), built once in the Adhérents list phase and reused. Check that the v9 Vue adapter is
  stable, otherwise stay on v8.
- **shadcn-vue** (MIT) used as a generator, not a dependency: it copies Reka + Tailwind components into the repo, which
  we then own and trim. No runtime package to follow.
- French formatting with `Intl` (`fr-FR`); plain validation functions per form (no form library).
- Icons: emojis as today (no dependency); Lucide (ISC) icon by icon only if needed.
- CSV export goes through a module that applies `csvSafe()` (formula injection), or uses the server-side export.
- Alternatives considered: Vuetify 4 (MIT, complete, best built-in responsive support, heavier, Material look), Quasar 2
  (MIT, CLI-centred), Element Plus (MIT, desktop oriented), PrimeVue 4.5.5 (MIT but frozen). Headless chosen to
  carry nothing unnecessary and keep each part replaceable, at the cost of building the components.

### D6 — Migration order (production checkpoint after each step)
1. **Foundation**: Vite + TS + Tailwind/Reka UI, responsive layout, `useAuth`, `/api/me`, Docker multi-stage build, CI job,
   then **Accueil**.
2. **Paramètres** and **Communications** (small, desktop only, admin, online only): settle the pattern
   (route, response models, generated types, forms).
3. **Planning** and **Outils**.
4. **Adhérents** merged with the phone **directory** (`/index`): first responsive + offline-read page.
5. **Compétitions**: desktop page merged with the phone PWA (outbox, HelloAsso payments, results). Then switch the
   service worker (D9), delete `alj-vue.js`, the old `web/` pages and the HTML string tests.

Coexistence: old and new pages are reached by full page loads; the Firebase session is shared (compat and modular SDKs
use the same IndexedDB store for the same project), so no second login.

### D7 — Tests
- **Vitest** for composables and pure logic (`useSyncedResource`, outbox, `useAuth` with Firebase mocked, API client,
  `csvSafe`, formatters, router role guards); the cases of
  `tests/web/sync_scripts_harness.js` are ported there.
- **Component tests** (Vitest + `@vue/test-utils`) only for components with logic (filters, validated forms). No
  snapshot tests.
- **Python Playwright e2e is the safety net**: before migrating a page, make sure its key flows are covered and move
  their selectors to `data-testid`.
- `tests/web/test_bureau_web.py`: per migrated page, delete the HTML string checks (`assertIn("btn-…", html)`), keep
  the API tests and move them to `tests/api/…`.

### D8 — Repo layout and dev loop
- `code_source/frontend/` (the deploy script only uploads `code_source/`): `package.json`, `package-lock.json`,
  `vite.config.ts`, `src/{pages,components,composables,api}`. npm; Node pinned by `.nvmrc` + `engines`, same version
  in the Dockerfile and CI.
- Dev: `uv run dev/run_server.sh` (FastAPI :8080, emulator) + `npm run dev` (Vite :5173, hot reload). Vite proxies
  `/api`, `/runtime-config.js` and the non-migrated pages to :8080.
- `runtime-config.js` stays served by FastAPI (emulator/production switch kept out of the build).
- Docker: a `node:<pinned>` stage builds `frontend/` into `/app/frontend-dist`, mounted by FastAPI. Deployment is
  unchanged (`./scripts/deploy_cloud_run.sh`, `gcloud run deploy --source .`). Never commit or upload a prebuilt
  output: `dist/` and `build/` are ignored at any depth by `.gitignore` and `.gcloudignore`.
- Update `README.md`, `AGENTS.md`, `code_source/AGENTS.md` and `code_source/dev/README.md` (commands, "all checks"
  line with `npm ci && npm run lint && npm run typecheck && npm test`).

### D9 — Service worker
Keep the current `sw.js` (network first) during the migration. Switch to the Workbox service worker generated by
`vite-plugin-pwa` (hashed precache, no hand-kept list or version bumps) only in step 5, once the phone routes are
migrated, so two service workers never compete for `/`.

### D10 — Outils: map and pivot stay as iframes, map rebuilt right after the migration
- During the migration, the Vue Outils page embeds `/map` (`src/api/reports/map.py`, Leaflet + markercluster from
  unpkg) and `/pivot` (`src/api/reports/pivot.py`, jQuery 3.6 + jQuery UI 1.12.1 + pivottable 2.23 from cdnjs) in
  sandboxed iframes, as today. They work, are isolated, and are not a priority on phones.
- **First follow-up after step 5**: rebuild the map as a Vue component with `leaflet` from npm and a JSON endpoint
  (`/api/reports/map-points`).
- The pivot stays an iframe. To do: upgrade or remove jQuery UI 1.12.1 (known CVEs; the sandbox limits the impact).

### D11 — One version number
Vite reads `code_source/VERSION` at build time and injects it into the app (shown in the UI). The separate web version
(`alj-web-version` in 9 `<meta>` tags, `CACHE_NAME` in `sw.js`) disappears with the old pages; the Workbox
precache is keyed by file hashes. Only `APP_VERSION` + `VERSION` remain to bump. `frontend/package.json` stays
`private: true`, version `0.0.0`.

### D12 — Supported browsers: Vite default target
Vite's default `build.target` ("baseline widely available": about Safari/iOS 16+, Chrome 107+), no
`@vitejs/plugin-legacy`. Older browsers (iOS ≤ 15) get a "browser not supported" message instead of a blank page.
Before step 1, check the user agents of `/competitions` in the Cloud Run request logs to confirm.

## Open questions
None. D2 confirmed (2026-10-21): offline mode is kept as is; usage by coaches at venues is not measured, so the outbox
stays (losing data entered at a venue is the worst failure for this app).
