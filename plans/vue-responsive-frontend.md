# Plan: Vue 3 responsive single-page frontend

> Source PRD: [#23 — PRD: Vue 3 responsive single-page frontend](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/23)
> Decision record: `documentations/plan_frontend_vue.md` (D1–D12)

## Architectural decisions

Durable decisions that apply across all phases:

- **Stack**: Vue 3 + Vite + TypeScript, vue-router, PrimeVue (styled mode, club theme preset: dark blue `1E3A8A`,
  orange `EA580C`, French locale). npm, Node version pinned and identical locally, in CI and in the Docker build
  stage. Vite default build target, no legacy bundle.
- **Routes (unchanged URLs, become SPA routes)**: `/bureau/` (Accueil), `/bureau/parametres`,
  `/bureau/communications`, `/bureau/planning`, `/bureau/outils`, `/bureau/adherents`, `/bureau/competitions`,
  `/index` (directory), `/competitions` (competitions + OAuth callback). At cutover, the phone and desktop variants
  resolve to the same responsive screens. Old URLs keep working (bookmarks).
- **Coexistence**: FastAPI serves the SPA entry page for migrated routes, the old HTML for the others; navigation
  between them is a full page load; the Firebase session is shared.
- **Served by FastAPI, outside the build**: `/runtime-config.js` (emulator / production switch), `/map`, `/pivot`,
  `/manifest.webmanifest`, `/sw.js` (current network-first worker until phase 12).
- **Auth**: unchanged Google implicit OAuth + Firebase `signInWithCredential`, callback on `/competitions`, emulator
  login in dev. The server is the only judge of roles.
- **New endpoint**: `GET /api/me` → `Me { email: string, role: "admin" | "coach" | "readonly" | null }`, computed by
  the existing server role logic (the `Role` enum, lower-cased; `null` = signed in without access); 401 without a
  valid token. French labels are a display concern of the frontend.
- **API contract**: Pydantic response models on every route a migrated screen calls; TypeScript types generated from
  `/openapi.json`; CI fails when they are stale. Writes and e-mail sends require `admin`.
- **Offline (per route)**: competitions = offline read + outbox; directory = offline read; every other screen online
  only. Same IndexedDB database as today (`alj-offline`: `resources`, `meta`, `outbox` stores), same wipe rules
  (logout, 401/403, user change) and 30-day limit — existing users' offline data carries over.
- **Version**: single version from `code_source/VERSION` (bumped with `APP_VERSION`), injected at build time.
- **Deployment**: unchanged script and Cloud Run service; multi-stage Dockerfile builds the frontend; build output
  never committed or uploaded. Each phase: test revision (0 % traffic, production data) → checks → promote.
- **Tests**: Vitest for deep modules and router guards; component tests only for components with logic; pytest for
  API; the existing Python Playwright e2e suite is the safety net, strengthened with `data-testid` selectors before
  each screen is migrated.

---

## Phase 1: SPA skeleton end to end

**User stories**: 11, 31, 33, 38, 39, 41, 46, 47, 48

### What to build

The thinnest path from source to production: a Vue app built in the Docker image and served by FastAPI on
`/bureau/`. It renders the responsive shell (sidebar on desktop, bottom tab bar on phones) with the club theme, the
Accueil cards linking to the existing old pages, and the app version read from `VERSION`. Unsupported browsers get a
message instead of a blank page. Locally, the Vite dev server (hot reload) proxies the API, the runtime config and the
old pages to FastAPI on the emulator stack. CI gains a frontend job. Sign-in is not handled yet: an anonymous visitor
sees a sign-in prompt that uses the existing flow.

### Acceptance criteria

- [ ] `/bureau/` is served from the built SPA in the container; every other page still serves the old HTML
- [ ] The shell switches between sidebar and bottom bar by screen width; no horizontal scroll on a phone
- [ ] The version shown in the UI equals `VERSION`
- [ ] An unsupported browser shows a "browser not supported" message
- [ ] `npm run dev` + the FastAPI dev server give one working URL for new and old pages
- [ ] CI runs install, lint, typecheck, unit tests and build for the frontend; the Docker build passes in CI
- [ ] Deploying with the unchanged script works on a test revision
- [ ] README, both AGENTS.md and the dev guide document the new commands and the "all checks" line
- [ ] Existing e2e suite still passes

---

## Phase 2: Sign-in and roles

**User stories**: 14, 25, 27, 28, 42

### What to build

`GET /api/me` on the server, the auth composable on the client (same Google flow, callback still on `/competitions`,
emulator login in dev) and router guards by role. Accueil greets the user with their role and only shows the cards
their role allows. A user signed in on an old page is signed in on the SPA and vice versa. The new code contains no
e-mail lists; the old pages keep theirs until phase 12.

### Acceptance criteria

- [ ] `/api/me` returns the right role for admin, coach, read-only and unknown accounts; 401 without a token
- [ ] Sign-in from the SPA returns to the page the user started from
- [ ] The session is shared between the SPA and old pages (no second sign-in)
- [ ] Guards: anonymous → sign-in prompt, wrong role → blocked/redirected, callback route always reachable
- [ ] Vitest covers the auth composable (Firebase mocked) and every role × route guard case
- [ ] pytest covers `/api/me`; the route is in the route inventory test
- [ ] e2e: sign-in, role display and logout on Accueil

---

## Phase 3: Typed API contract + Paramètres

**User stories**: 23, 36, 37

### What to build

The contract pipeline, proven on one screen: Pydantic response models on the routes Paramètres calls, TypeScript
types generated from OpenAPI, a CI check that fails when they are stale, and the typed API client (token, error
mapping to `{ status, code, message }`). Paramètres (Google connection, database status and services) is migrated
to the SPA.

### Acceptance criteria

- [ ] Paramètres routes declare response models; generated types are used by the page
- [ ] Changing a response model without regenerating types fails CI
- [ ] Vitest covers the API client (token added, error mapping, network failure)
- [ ] e2e Paramètres flows moved to `data-testid` before the migration and pass after it
- [ ] HTML string checks for Paramètres removed from the bureau web tests; its API tests kept

---

## Phase 4: Communications

**User stories**: 20

### What to build

E-mail template management (list, create, edit, delete) in the SPA with PrimeVue forms and dialogs, on typed
routes with response models. Admin only.

### Acceptance criteria

- [ ] Template CRUD works end to end and is persisted through the existing repository
- [ ] Non-admin roles cannot reach the screen or call the writes
- [ ] Component tests for the validated template form
- [ ] e2e Communications flows strengthened first, pass after migration; HTML string checks removed

---

## Phase 5: Planning

**User stories**: 21

### What to build

Slot planning in the SPA: visual and table views, create / edit / delete slots, animateurs and tarifs, print the
grid and export it to Excel (server-generated file, club style), on typed routes.

### Acceptance criteria

- [ ] Slot CRUD, print and Excel export work as on the old page
- [ ] Usable on a phone (read and edit)
- [ ] e2e Planning flows strengthened first, pass after migration; HTML string checks removed

---

## Phase 6: Outils

**User stories**: 19, 22

### What to build

The Outils screen in the SPA: tabs embedding `/map` and `/pivot` in sandboxed iframes as today, FFME stats, import
(preview and apply) and export. The CSV export module (formula-injection rule) is introduced here and used by every
table export from now on.

### Acceptance criteria

- [ ] Map and pivot tabs load in sandboxed iframes with the season filter
- [ ] FFME preview / apply / export work; the FFME golden master test stays byte-identical
- [ ] Vitest covers the CSV export module (formula cases; signed numbers and phone numbers kept)
- [ ] e2e Outils flows strengthened first, pass after migration; HTML string checks removed

---

## Phase 7: Adhérents list (online)

**User stories**: 9, 15, 16, 19, 35

### What to build

The member list on the synced-resource composable in online mode (ETag polling, refresh on visibility and network
return) and a PrimeVue data table: filters (season, tarif, …), sorting, pagination, CSV export through the safe
export module, stacked rows on phones. Read-only in this phase; the old page's record actions link to the old page
until phase 8.

### Acceptance criteria

- [ ] Filters and columns match the old page (including diploma and city)
- [ ] Data refreshes while the screen is open; unchanged polls are 304
- [ ] Nothing is stored offline for this route
- [ ] Vitest covers the synced resource in online mode (polling, 304, stop, refresh)
- [ ] e2e member list flows strengthened first, pass after migration

---

## Phase 8: Member record

**User stories**: 17, 18, 26

### What to build

Member record in the SPA: view, edit, add a member, send an e-mail and an attestation from the record. Writes and
sends are admin only and go through the existing repository so Firestore stays the source of truth. No member data
is cached on the device.

### Acceptance criteria

- [ ] Edit and add persist and replicate as today; validation errors are shown on the form
- [ ] E-mail and attestation sends work and record the sent date
- [ ] Non-admin roles see the record read-only (or not at all, per role) and cannot call writes
- [ ] Component tests for the member form validation
- [ ] e2e member edit / add / e-mail / attestation flows pass; remaining Adhérents HTML string checks removed

---

## Phase 9: Directory merged, offline read

**User stories**: 12, 13, 14, 29, 30

### What to build

`/index` becomes the responsive read-only directory of the SPA (contact and emergency details per role), replacing
the phone directory page. Offline mode of the synced-resource composable arrives here: the IndexedDB copy is read
when the network is down, and wiped on logout, 401/403 and user change, expiring after 30 days. Existing offline data
from the old page carries over.

### Acceptance criteria

- [ ] The directory works on phone and desktop; read-only users see only what their role allows
- [ ] With the network off, the last data is shown with its age
- [ ] Logout, 401/403, a different user and a 31-day-old copy all leave no data on the device
- [ ] Vitest covers the offline store and the synced resource in offline mode (load, expiry, wipe rules)
- [ ] e2e offline directory scenarios pass

---

## Phase 10: Compétitions, read only

**User stories**: 1, 2, 3, 9, 10

### What to build

One responsive competitions screen replacing both the desktop and the phone pages, served on `/competitions` and
`/bureau/competitions`: competitions, participants and payment status, refreshing on its own, readable offline. The
OAuth callback keeps working on this route. Writes still go through the old page (linked) until phase 11.

### Acceptance criteria

- [ ] Both URLs show the same screen; usable one-handed on a phone
- [ ] Offline read shows the last data; wipe rules as in phase 9
- [ ] Sign-in through Google still completes on `/competitions`
- [ ] The app still installs and opens as a PWA
- [ ] e2e competitions read, offline and auth scenarios pass

---

## Phase 11: Compétitions writes + outbox

**User stories**: 4, 5, 6, 7, 8, 24

### What to build

All competitions writes in the SPA: participant changes, HelloAsso payments, results fetching, competition e-mails.
The outbox module queues changes made offline, replays them when the network returns, shows the pending count,
warns before logout with unsent changes, and reports server refusals (e.g. `already_paid`). Existing queued entries
from the old page are replayed.

### Acceptance criteria

- [ ] Offline edits are queued, shown as pending, and sent when the network returns
- [ ] Logout with pending changes asks for confirmation
- [ ] A refused change shows the server's reason and leaves the queue consistent
- [ ] HelloAsso payment and results fetching work (fakes in e2e)
- [ ] Vitest covers the outbox (queue / replace by key, replay order, refusal codes, clear)
- [ ] e2e competitions write, offline outbox and HelloAsso scenarios pass; competitions HTML string checks removed

---

## Phase 12: Cutover

**User stories**: 10, 32, 40, 42

### What to build

Remove the old frontend. Switch to the build-generated Workbox service worker (hashed precache), delete the
desktop/phone redirect script, the old pages and shared scripts, the separate web version, the remaining hardcoded
e-mail lists and their mirror test, and the leftover HTML string tests. Every former URL resolves to its SPA screen.

### Acceptance criteria

- [ ] Clients on the old service worker update to the new one without a manual refresh or a broken page
- [ ] No hand-kept precache list or cache-name bump remains
- [ ] Every former URL (with and without `?vue=` parameters) opens the right screen
- [ ] No e-mail address list remains in any frontend file
- [ ] The full e2e suite passes; docs no longer mention the old pages
- [ ] Follow-up issue opened for the map rebuild and the jQuery UI upgrade
