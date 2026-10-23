# Plan: Vue 3 responsive single-page frontend

> Source PRD: [#23 — PRD: Vue 3 responsive single-page frontend](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/23)
> Decision record: `documentations/plan_frontend_vue.md` (D1–D13)

## Architectural decisions

Durable decisions that apply across all phases:

- **Stack**: Vue 3 + Vite + TypeScript, vue-router; UI = Reka UI (headless) + Tailwind CSS v4 + TanStack Table,
  components generated with shadcn-vue and owned in the repo (club tokens: dark blue `1E3A8A`, orange `EA580C`,
  Segoe UI; French formatting with `Intl`). Every dependency MIT or equivalent (decision record D5). npm, Node version pinned and identical locally, in CI and in the Docker build
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

## Phase 1: SPA skeleton end to end, with sign-in

**User stories**: 11, 27, 28, 31, 33, 38, 39, 41, 42, 46, 47, 48

> Scope revised when phase 1 started (2026-10-22): today's `/bureau/` already refuses non-staff accounts (checked by
> the e2e suite), so shipping Accueil without sign-in would be a production regression. Sign-in and `GET /api/me`
> move here from phase 2.

### What to build

The thinnest path from source to production, at parity with today's Accueil: a Vue app built in the Docker image and
served by FastAPI on `/bureau/`. It renders the responsive shell (sidebar on desktop, bottom tab bar on phones) with
the club theme, the Accueil cards linking to the existing old pages, and the app version read from `VERSION`.
Sign-in uses the existing flow (through `/competitions?login=1`, emulator picker in dev), the role comes from
`GET /api/me`, non-staff accounts get the "access reserved" gate, and the club Google token warning is shown when it
has expired. Unsupported browsers get a message instead of a blank page. Locally, the Vite dev server (hot reload)
proxies the API, the runtime config and the old pages to FastAPI on the emulator stack. CI gains a frontend job.
The shell keeps the element ids the e2e suite already uses, so the existing tests check the new page unchanged.

### Acceptance criteria

- [x] `/bureau/` is served from the built SPA; every other page still serves the old HTML
- [x] The shell switches between sidebar and bottom bar by screen width; no horizontal scroll on a phone
- [x] The version shown in the UI equals `VERSION`
- [x] An unsupported browser shows a "browser not supported" message
- [x] `/api/me` returns the right role for admin, coach, read-only and unknown accounts; 401 without a token
- [x] Sign-in, logout, session shared with the old pages, gate for non-staff, Google token warning: the existing
      e2e auth, smoke and service-worker tests pass against the SPA (only the sign-in helper gained an SPA branch;
      `alj-vue.js` no longer redirects while the emulator's redirect sign-in is pending)
- [x] `npm run dev` + the FastAPI dev server give one working URL for new and old pages
- [ ] CI runs install, lint, typecheck, unit tests and build for the frontend; the e2e job builds the SPA first
      (workflow written; not yet run on GitHub)
- [ ] Deploying with the unchanged script works on a test revision
- [x] README, both AGENTS.md and the dev guide document the new commands and the "all checks" line

---

## Phase 2: Router guards and role-aware navigation

**User stories**: 14, 25

### What to build

Role guards in the router (anonymous → sign-in gate, wrong role → blocked, callback route always reachable) and a
navigation and Accueil that only show what the user's role allows. Small on its own, it lands just before the first
admin-only screens.

### Acceptance criteria

Screens per role: decision record D13 (Paramètres and Communications admin only).

- [x] Guards: anonymous → sign-in prompt, wrong role → blocked/redirected, callback route always reachable
- [x] Vitest covers every role × route guard case and the auth composable (Firebase mocked)
- [x] Navigation and Accueil cards follow the role
- [x] e2e: role display and navigation per role

---

## Phase 3: Typed API contract + Paramètres

**User stories**: 23, 36, 37

### What to build

The contract pipeline, proven on one screen: Pydantic response models on the routes Paramètres calls, TypeScript
types generated from OpenAPI, a CI check that fails when they are stale, and the typed API client (token, error
mapping to `{ status, code, message }`). Paramètres (Google connection, database status and services) is migrated
to the SPA.

### Acceptance criteria

- [x] Paramètres routes declare response models; generated types are used by the page
- [x] Changing a response model without regenerating types fails CI (`dev/export_openapi.py --check`, `npm run check:api`;
  both verified locally, the workflow not yet run on GitHub)
- [x] Vitest covers the API client (token added, error mapping, network failure)
- [x] e2e Paramètres flows moved to `data-testid` before the migration and pass after it
- [x] HTML string checks for Paramètres removed from the bureau web tests; its API tests kept

---

## Phase 4: Communications

**User stories**: 20

### What to build

E-mail template management (list, create, edit, delete) in the SPA with the repo's form and dialog components, on typed
routes with response models. Admin only.

### Acceptance criteria

- [x] Template CRUD works end to end and is persisted through the existing repository (the server now also refuses
  a duplicate name, 409, and an invalid sender address)
- [x] Non-admin roles cannot reach the screen or call the writes
- [x] Component tests for the validated template form
- [x] e2e Communications flows strengthened first, pass after migration; HTML string checks removed

---

## Phase 5: Planning

**User stories**: 21

### What to build

Slot planning in the SPA: visual and table views, create / edit / delete slots, animateurs and tarifs, print the
grid and export it to Excel (server-generated file, club style), on typed routes.

### Acceptance criteria

- [x] Slot CRUD, print and Excel export work as on the old page
- [x] Usable on a phone (read and edit)
- [x] e2e Planning flows strengthened first, pass after migration; HTML string checks removed

> Done 2026-10-22. Coaches and admins change the slots (`/api/planning/item`); replacing the whole planning
> (`POST /api/planning`) stays admin only. Editing a slot keeps a day or tariff missing from the form's lists (« Lundi /
> Jeudi », a former season's tariff), which the old page dropped. TanStack Table waits for Adhérents: this
> table is small and needs no sorting or paging. The week grid still has no Sunday column, like the Excel grid.

---

## Phase 6: Outils

**User stories**: 19, 22

### What to build

The Outils screen in the SPA: tabs embedding `/map` and `/pivot` in sandboxed iframes as today, FFME stats, import
(preview and apply) and export. The CSV export module (formula-injection rule) is introduced here and used by every
table export from now on.

### Acceptance criteria

- [x] Map and pivot tabs load in sandboxed iframes with the season filter
- [x] FFME preview / apply / export work; the FFME golden master test stays byte-identical
- [x] Attendance sheets tab kept: course sheets (one workbook or a zip) and the autonomous sheet download, covered by
      e2e (`test_course_attendance_sheets`, `test_autonomous_attendance_sheet`)
- [x] The FFME « Importer & Fusionner directement » button (no preview) kept, admins only, behind a confirmation
- [x] Vitest covers the CSV export module (formula cases; signed numbers and phone numbers kept)
- [x] e2e Outils flows strengthened first, pass after migration; HTML string checks removed

> Done 2026-10-22. The attendance sheets tab moved too (it was on the old page). The CSV module is `lib/csv.ts`
> (`toCsv`, `csvSafe`); Outils has no table export of its own, the FFME CSV stays generated by the server. The FFME
> import is shown to admins only (the server already refused it to coaches); `/api/ffme/import` now always matches
> the file again itself and only takes the manual matches from the page (the old page sent back the matches of the
> preview). « Toutes les saisons » in the pivot table now really shows every season (the old page fell back to
> 2026-2027).

**TODO (FFME import, to think through)**: the manual matches of the import behave oddly. A row of the file can be
linked by hand to a member the file already matched automatically: `apply_ffme_matches` then writes that member twice
and the last write wins (licence, passports, diplomas and health document of the wrong row). `user_id` is never checked
against the season's members either (an unknown id is written for nothing, silently). Decide what a manual match may
target (members left unmatched only? any member of the season?), refuse the rest in `/api/ffme/import`, and filter the
pickers of the page the same way.

---

## Phase 7: Adhérents list (online)

**User stories**: 9, 15, 16, 19, 35

### What to build

The member list on the synced-resource composable in online mode (ETag polling, refresh on visibility and network
return) and the repo's responsive data table component (TanStack Table, built in this phase): filters (season, tarif, …), sorting, pagination, CSV export through the safe
export module, stacked rows on phones. Read-only in this phase; the old page's record actions link to the old page
until phase 8.

### Acceptance criteria

- [x] Filters and columns match the old page (including diploma and city)
- [x] Data refreshes while the screen is open; unchanged polls are 304
- [x] Nothing is stored offline for this route
- [x] Vitest covers the synced resource in online mode (polling, 304, stop, refresh)
- [x] e2e member list flows strengthened first, pass after migration

> Done 2026-10-22. The former page stays on `/bureau/adherents-fiche` as the member record (edit, add, e-mail,
> attestation): the list links each name to `?id=<user_id>&saison=…` and « Ajouter un adhérent » to `?ajout=1`; it gets
> a « Liste des adhérents » link back. The list has no detail pane of its own (the record comes in phase 8). Pages of 50
> rows; the CSV export holds every page, in the table's order. The filters are remembered as before (same
> `localStorage` key as the record page), except the search, which often holds a member's name. `GET /api/members` has
> a response model (`MemberList`); its body is still built by hand (ETag), a test checks it matches the model.

---

## Phase 8: Member record

**User stories**: 17, 18, 26

### What to build

Member record in the SPA: view, edit, add a member, send an e-mail and an attestation from the record. Writes and
sends are admin only and go through the existing repository so Firestore stays the source of truth. No member data
is cached on the device.

### Acceptance criteria

- [x] Edit and add persist and replicate as today; validation errors are shown on the form
- [x] E-mail and attestation sends work and record the sent date
- [x] Non-admin roles see the record read-only (coaches can still e-mail the member) and cannot call writes
- [x] Component tests for the member form validation
- [x] e2e member edit / add / e-mail / attestation flows pass; remaining Adhérents HTML string checks removed

> Done 2026-10-22. The record is a dialog of Adhérents, in the URL (`?id=<user_id>&saison=…&achat=<purchase_id>`,
> `?ajout=1`): the former page's links still open it, and `/bureau/adherents-fiche` (2.14) redirects there. It is read
> from the polled list, so it follows the server after each write; one dialog shows the record, the edit form, the
> e-mail or the certificate in turn. `web/bureau/adherents.html`, `alj-members.js` and `alj-filters.js` are removed.
> The routes are typed: `/api/members/update` writes only the fields sent and refuses invalid e-mails, badges and
> statuses (422); `/api/members/create` refuses a non-ISO birth date. The certificate routes now take the
> membership (`purchase_id`, season) and read the amount, payer and status from the database instead of trusting a
> member object sent by the page; an accented name no longer breaks the PDF's `Content-Disposition` header.
> `/api/send-email` keeps its body (the competitions pages call it too) and gets a response model. Coaches send e-mails
> too, from the record as from a competition (the server limits them to known members); editing, adding and the
> certificate stay admin only. The
> server's refusal of a coach's write is covered by the `required_role` tests: the e2e stack runs without auth.

---

## Phase 9: Directory merged, offline read

**User stories**: 12, 13, 14, 29, 30

### What to build

`/index` becomes the responsive read-only directory of the SPA (contact and emergency details per role), replacing
the phone directory page. Offline mode of the synced-resource composable arrives here: the IndexedDB copy is read
when the network is down, and wiped on logout, 401/403 and user change, expiring after 30 days. Existing offline data
from the old page carries over.

### Acceptance criteria

- [x] The directory works on phone and desktop; read-only users see only what their role allows
- [x] With the network off, the last data is shown with its age
- [x] Logout, 401/403, a different user and a 31-day-old copy all leave no data on the device
- [x] Vitest covers the offline store and the synced resource in offline mode (load, expiry, wipe rules)
- [x] e2e offline directory scenarios pass

> Done 2026-10-22. `/index` is the Vue route `annuaire` (`DirectoryPage.vue`), in the menu (« 📇 Annuaire ») and on
> Accueil; desktops are no longer sent to `/bureau/` from it. Tabs on phones (Adhérents, Urgences, Filtres), filters
> beside the list on desktop; same filters as Adhérents (`adherents/members.ts`), remembered under the former page's key
> (`alj_annuaire_filters`), without the search. Read-only accounts keep the « Accès réservé » gate, as before
> (`/api/members` is for coaches and admins); nothing is asked nor read from the device for them.
> Only contacts, emergency contacts and diplomas are kept on the device (`annuaire/directory.ts`): the directory no
> longer shows the health lines (engagement, document) nor the order (date, reference, amount) of the former page;
> they stay in the Adhérents record, online. One copy per device: the last season viewed.
> `lib/store.ts` is `alj-store.js` in TypeScript, same database: the competitions page's copy is read and wiped by
> the app too. The former directory kept nothing offline (it was online only): there was nothing of its own to carry
> over. The store is opened on every page of the app (`bindOfflineStore`), so that another account signing in wipes
> it. Offline, `/api/me` cannot answer: the auth state says why (`offline`), and the directory then opens on the copy
> of the signed-in user (verdict `offline`), and asks the server again when the network comes back. `/annuaire/` and
> `/annuaire/index.html` redirect to `/index`; `web/index.html` and `alj-members-sync.js` are removed. Vitest runs the
> store on `fake-indexeddb` (Apache-2.0, dev only, no dependencies).
>
> Changed 2026-10-23: the menu and the Accueil cards list the directory on phones and Adhérents on computers (below /
> from the `md` breakpoint of the menu, by CSS only: `screen` in `lib/access.ts`). Both addresses still open on any
> screen, without redirect; a member's full record (health, order, edits) stays in Adhérents. The directory keeps its
> offline copy of the season and Compétitions its copy of the competitors: both kept on purpose.

---

## Phase 10: Compétitions, read only

**User stories**: 1, 2, 3, 9, 10

### What to build

One responsive competitions screen replacing both the desktop and the phone pages, served on `/competitions` and
`/bureau/competitions`: competitions, participants and payment status, refreshing on its own, readable offline. The
OAuth callback keeps working on this route. Writes still go through the old page (linked) until phase 11.

### Acceptance criteria

- [x] Both URLs show the same screen; usable one-handed on a phone
- [x] Offline read shows the last data; wipe rules as in phase 9
- [x] Sign-in through Google still completes on `/competitions`
- [x] The app still installs and opens as a PWA
- [x] e2e competitions read, offline and auth scenarios pass

> Done 2026-10-22. `CompetitionsPage.vue` answers `/competitions` and `/bureau/competitions`: the list, then a
> competition's participants (`?id=`) grouped by slot group, with « Participe », payment status, KPIs and filters
> (Tous / Participe / Paiement en attente); the list and the competition side by side on desktop, one at a time on a
> phone. Read-only accounts open it too (new access level `viewer`: their menu has Compétitions only), without phones,
> emergency contacts nor HelloAsso orders, as on the former page. The former pages keep the writes: the phone one on
> `/competitions/gestion`, the office one on `/bureau/competitions-gestion` (« ✏️ Gérer les compétitions », coaches and
> admins); HelloAsso, coaches and balance stay there. The former phone page now signs in through
> `/competitions?login=1` (its new address is no OAuth redirect URI). The Google callback (access token in the
> fragment, state checked), `?login=1` and the emulator's redirect are handled when the app starts (`signIn.ts`,
> `lib/oauth.ts`, same client and scopes). Offline copies keep the former page's names (`competitions`, `competitors`):
> its copies (no url recorded) are shown by the app. The member directory (`/api/competition-members`) only gives the
> tariff and slot group, online. Response models: `Competition` (stored fields not listed are allowed),
> `CompetitorContact`, `CompetitionMember`. The two offline screens are in the main bundle (a page loaded on demand is
> missing offline when it was never opened online). With both entry pages in the app, `alj-vue.js` (desktop/phone
> redirection) and the « 📱 Version mobile » links are removed; `/` still goes to `/competitions`. The entry page
> gained the PWA tags (manifest, Apple icons).

---

## Phase 11: Compétitions writes + outbox

**User stories**: 4, 5, 6, 7, 8, 24

### What to build

All competitions writes in the SPA, i.e. every tool of the two former pages (`web/competitions.html`,
`web/bureau/competitions.html`), since phase 12 deletes them: participant changes, HelloAsso payments, results
fetching, competition e-mails, and also competition create / edit / delete, archive / restore and « archive past »,
coaches management, the balance (bilan) report with its CSV export, and the per-competition CSV export. The outbox module queues changes made offline, replays them when the network returns, shows the pending count,
warns before logout with unsent changes, and reports server refusals (e.g. `already_paid`). Existing queued entries
from the old page are replayed.

### Acceptance criteria

- [x] Offline edits are queued, shown as pending, and sent when the network returns
- [x] Logout with pending changes asks for confirmation
- [x] A refused change shows the server's reason and leaves the queue consistent
- [x] HelloAsso payment and results fetching work (fakes in e2e)
- [x] Competitions can be created, edited, deleted, archived and restored; past ones archived in one action
- [x] Coaches can be added, renamed and deleted; the balance report and both CSV exports work
- [x] No tool of the former competitions pages is left out of the SPA before they are removed
- [x] Vitest covers the outbox (queue / replace by key, replay order, refusal codes, clear)
- [x] e2e competitions write, offline outbox and HelloAsso scenarios pass; competitions HTML string checks removed

> Done 2026-10-23 (in the « competition page » commit; boxes ticked with phase 12's full e2e run). Every tool of the
> two former pages is in `CompetitionsPage.vue` and `pages/competitions/` (forms, HelloAsso, coaches, balance panes).
> Offline, « Participe » and « Présent » of a listed competitor are queued (`outbox.ts`, same `outbox` store and entries
> as the former phone page, Vitest `outbox.test.ts`); e2e: `test_offline.py`, `test_helloasso.py`, `test_competitors.py`,
> `test_competitions_manage.py`, `test_coaches_balance.py`, `test_competition_email.py`.

---

## Phase 12: Cutover

**User stories**: 10, 32, 40, 42

### What to build

Remove the old frontend. Switch to the build-generated Workbox service worker (hashed precache), delete the
desktop/phone redirect script, the old pages and shared scripts, the separate web version, the remaining hardcoded
e-mail lists and their mirror test, and the leftover HTML string tests. Every former URL resolves to its SPA screen.

### Acceptance criteria

- [x] Clients on the old service worker update to the new one without a manual refresh or a broken page
- [x] No hand-kept precache list or cache-name bump remains
- [x] Every former URL (with and without `?vue=` parameters) opens the right screen
- [x] No e-mail address list remains in any frontend file
- [x] The full e2e suite passes; docs no longer mention the old pages
- [x] Follow-up issue opened for the map rebuild and the jQuery UI upgrade (#25)

> 2026-10-23 (2.18.0). Service worker: `frontend/src/sw.ts` (Workbox, `vite-plugin-pwa` in `injectManifest` mode, classic
> script), built into `dist/sw.js` and served by FastAPI at `/sw.js` (`no-cache`), the address and scope of the former
> `web/sw.js`: browsers that have it install the new one on their next visit (`skipWaiting` + `clientsClaim`), and it
> deletes the former `alj-escalade-v*` caches. Precache = every build file (hashed names, `/spa/…`) and the entry page;
> app pages are network first, the precached entry page offline (`/` too: the router redirects it to `/competitions`);
> the API, `/runtime-config.js`, the manifest, `/map` and `/pivot` are never cached. A page left open across a deploy
> reloads once when one of its chunks is gone (`vite:preloadError`). The app registers the worker in builds only (not
> in `npm run dev`). Removed: `web/shared/` (scripts, CSS, the last role e-mail lists), `web/sw.js`, the `/static-web`
> mount, the separate web version (`/api/web-version` now answers `AppVersion { app_version }`), the role-list mirror
> test, the HTML / shared-script string tests and the Node harness of `alj-sync.js`; a test now checks that no frontend
> file holds a role e-mail. `web/` keeps the manifest and the logo (`/annuaire/assets/logo.png`). Former page files of
> the `/annuaire` mount (`/annuaire/competitions.html`, `/annuaire/bureau/…`) redirect to their screen, query kept.
> e2e: `test_service_worker.py` covers the precache, offline pages and the update from a former worker.
>
> Closed 2026-10-23: full e2e suite green locally (`-n 1`), the last docstrings describing `web/competitions.html` as
> live updated; remaining mentions are « former … » notes, and `GEMINI.md` (known stale, see `ARCHITECTURE.md`).
