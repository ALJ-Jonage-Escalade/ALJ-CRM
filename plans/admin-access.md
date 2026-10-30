# Plan: Administration page — access roles (Accès)

> Source PRD: [#68](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/68). Branch: `feat/admin_page`.
> Shipped as **one release**: phase 1 removes the hardcoded roles, so production gets the whole plan at once, after
> the deploy-day migration (phase 8).

## Architectural decisions

Durable decisions that apply across all phases:

- **Single source of roles**: the Firestore roles collection. The club-domain rule (`ADMIN_EMAIL_DOMAINS`), the lists
  `ADMIN_EMAILS` / `COACH_EMAILS` / `READONLY_EMAILS` and the custom claims (`admin`, `coach`, `readonly`) are removed.
  A verified Google e-mail (`email_verified`) stays required. The one exception is the bootstrap address.
- **Collections** (server only, no `crm_` prefix: not copied into the SQLite cache; `firestore.rules` already blocks
  every client):
  - `access_roles`: document id = normalised e-mail (trimmed, lower case). `role` (`admin` | `coach` | `readonly`),
    `display_name`, `last_sign_in_at`, `created_at`, `created_by`, `updated_at`, `updated_by`.
  - `access_requests`: document id = normalised e-mail. `google_display_name`, `first_requested_at`,
    `last_requested_at`, `dismissed_at`. A dismissed address is ignored for 30 days; untouched requests older than
    30 days are deleted on read.
  - `access_history`: write-once entries. `at`, `author` (e-mail or `bootstrap`), `action` (`added` |
    `role_changed` | `name_changed` | `removed` | `request_granted` | `request_dismissed` | `bootstrap`),
    `target_email`, `old_role`, `new_role`.
- **Module layers**: an access store (Firestore I/O, supports create-if-absent), a role directory (`role_of(email)`,
  `invalidate()`; store, clock and bootstrap address passed in; 60 s in-memory cache) and access rules (operations,
  safeguards, history, invalidation). Tests use fakes passed in, not patches.
- **Directory failure**: when the store can't be read and the cache has expired, every address except the bootstrap
  one gets "access unavailable", which the API answers with **503**, never 403. The frontend keeps its "role could not
  be checked" state, so offline mode keeps working.
- **Routes** (router `src/api/admin/access.py`, admin role on every method, listed among the Firestore-only routers in
  `server.py` and in `tests/test_route_inventory.py`; Pydantic response models + `error_responses()`):
  - `GET /api/admin/access/roles` · `POST /api/admin/access/roles`
  - `PATCH /api/admin/access/roles/{email}` (role and/or display name) · `DELETE /api/admin/access/roles/{email}`
  - `GET /api/admin/access/requests` · `POST /api/admin/access/requests/{email}/grant` (body: role, display name)
    · `DELETE /api/admin/access/requests/{email}` (dismiss)
  - `GET /api/admin/access/history` (latest first, limited)
  - Errors: 400 validation, 409 safeguard refusals, French messages shown as-is by the page.
- **`/api/me`**: same answer. As a side effect it records the sign-in date (with a role) or an access request (without
  a role); it passes on a 503.
- **Bootstrap**: `BOOTSTRAP_ADMIN_EMAIL`, read through the secret store and set once on the Cloud Run service (kept by
  every deploy from GitHub). Created if absent at startup, never overwritten, skipped in dev mode, never blocks startup.
- **Frontend**: page id `administration` (access `admin`) in `lib/access.ts`, route `/bureau/administration`; first
  sub-page `acces` (index route, offline `none`). API calls go through `services/admin.ts`.

---

## Phase 1: Roles come from Firestore

**User stories**: 13, 31, 32, 33, 35

### What to build

Swap the source of truth for roles. The role directory loads `access_roles` through the access store, keeps the list
for 60 seconds and answers "unavailable" when the store fails after the cache expires. `role_for_claims` keeps the
verified e-mail check, then asks the directory; the middleware and `/api/me` turn "unavailable" into 503. The
hardcoded lists, the domain rule and the custom-claims checks are deleted, so no personal address is left in the code.
The emulator seed writes `access_roles` entries for the dev accounts (admin, coach, read-only) instead of custom claims.

### Acceptance criteria

- [ ] The dev accounts sign in on the emulator with the same roles as before, without custom claims
- [ ] A club-domain address with no entry, and a token with a custom claim but no entry, get no role
- [ ] An unverified e-mail gets no role, even if it is listed
- [ ] Directory unit tests: listed role, unknown address, case/whitespace, cache served within 60 s and reloaded after,
      `invalidate()` takes effect at once, "unavailable" when the store fails after expiry
- [ ] `api_auth` tests: 503 when the directory is unavailable (on a protected route and on `/api/me`)
- [ ] No personal e-mail address left in `src/` (grep)

---

## Phase 2: Bootstrap admin

**User stories**: 25, 26, 27, 28, 29, 30, 34, 37, 38

### What to build

At application startup, read `BOOTSTRAP_ADMIN_EMAIL`. If that address has no entry, create it as admin with
create-if-absent and write one `bootstrap` history entry. An existing entry is never touched. The directory always
answers admin for that address, even with an empty list or an unreadable store. The step is skipped in dev mode, logs a
warning when the setting is empty, and logs (never raises) any error. The Cloud Run setup guide documents the one-time
`gcloud run services update … --update-env-vars BOOTSTRAP_ADMIN_EMAIL=…` command (which creates a revision that goes
live at once), the rollback caveat (a revision older than the setting has no emergency access, but keeps the list) and
the 503 behaviour when Firestore is down.

### Acceptance criteria

- [ ] Fresh store + setting → one admin entry and one `bootstrap` history entry
- [ ] Two concurrent bootstraps (fake store) → a single entry and a single history entry
- [ ] An existing entry for that address (e.g. demoted to coach) is kept as is
- [ ] The bootstrap address is admin with an empty list and with an unreadable store; others get 503
- [ ] Dev mode: no bootstrap; empty setting: warning logged; store error: logged, startup continues
- [ ] Setup guide updated (command, rollback caveat, 503 behaviour)

---

## Phase 3: Administration page with the read-only Accès list

**User stories**: 1, 2, 3, 4

### What to build

Create the `admin` theme router with `GET /api/admin/access/roles` (e-mail, display name, role, last sign-in date).
On the frontend, add the `administration` page (admin access) with its first sub-page `acces`, at
`/bureau/administration`, served by the server's SPA routes. The Accès sub-page shows the table of entries. The page is
hidden from the menu and refused by the router guards for coach and read-only users, and is online only.

### Acceptance criteria

- [ ] An admin sees « Administration » in the menu and the Accès table lists the seeded entries
- [ ] Coach and read-only: no menu entry; typing the address redirects as for other admin pages; the API answers 403
- [ ] Offline: the sub-page is disabled ("En ligne uniquement")
- [ ] Route inventory test, Firestore-only router list, OpenAPI contract and generated types updated
- [ ] Vitest: menu/router shows Administration only to admins; the table renders the API answer

---

## Phase 4: Managing entries

**User stories**: 5, 6, 7, 8, 9, 10, 11, 12

### What to build

Add the access-rules operations grant, change role, rename and remove, exposed as POST, PATCH and DELETE on
`/api/admin/access/roles`. E-mails are validated and normalised with the existing validators. Duplicates are refused
(400); self-removal, self-demotion and removing or demoting the last admin are refused (409). Each change writes one
`access_history` entry and invalidates the directory on that instance. The Accès sub-page gets the add form (e-mail,
role, display name), inline role and name editing, and removal after confirmation, and shows the server's messages.

### Acceptance criteria

- [ ] Unit (fake store): each operation writes the right entry and exactly one history entry
- [ ] Duplicate add, invalid e-mail → 400; self-removal, self-demotion, last-admin removal/demotion → 409, French message
- [ ] A change is seen at once on the same instance (directory invalidated)
- [ ] TestClient: coach and read-only get 403 on every write; success bodies match the response models
- [ ] Vitest: add, change role, rename, remove after confirmation, refusal message shown

---

## Phase 5: Historique block

**User stories**: 22, 23

### What to build

Expose `GET /api/admin/access/history` (latest first, limited) and show a read-only « Historique » block on the Accès
sub-page: date, author, action, target, old → new role. No route edits or deletes history.

### Acceptance criteria

- [ ] Changes made in phase 4 appear newest first with author and old/new role
- [ ] No write route exists on history (route inventory)
- [ ] TestClient: admin-only; Vitest: the block renders the entries

---

## Phase 6: Access requests

**User stories**: 14, 15, 16, 17, 18, 19, 20, 21

### What to build

When `/api/me` sees a signed-in account without a role, it records an access request (one per address, updating
`last_requested_at` on repeat sign-ins; nothing while dismissed less than 30 days ago). The no-role screen tells the user
their request was sent to the club's admins. The Accès sub-page gets a « Demandes d'accès » block (e-mail, Google display
name, date) with "grant" (role picker → creates the entry, removes the request, history `request_granted`) and
"dismiss" (history `request_dismissed`). Requests untouched for 30 days are deleted on read.

### Acceptance criteria

- [ ] Unit: repeated sign-in updates a single request; a dismissed address isn't recorded again for 30 days; requests
      older than 30 days are dropped; a granted request becomes an entry and leaves the requests
- [ ] `/api/me` without a role records the request; with a 503 it records nothing and passes the 503 on
- [ ] Vitest: grant with a role, dismiss, no-role message
- [ ] e2e (emulator): a new account signs in and is refused, appears as a request, the admin grants it coach, the
      account then opens a coach page

---

## Phase 7: Last sign-in date

**User stories**: 24

### What to build

When `/api/me` answers a signed-in user with a role, record `last_sign_in_at`, at most once a day per person (to limit
Firestore writes). The Accès table shows the date.

### Acceptance criteria

- [ ] Unit: first sign-in of the day writes, later ones the same day don't, next day writes again (fake clock)
- [ ] A write failure doesn't fail `/api/me`
- [ ] The Accès table shows the date (or « jamais »)

---

## Phase 8: Deploy day and docs

**User stories**: 36 (plus the docs and versioning items of the PRD)

### What to build

A one-off migration script in the git-ignored `scripts_temporaires/` writes today's users (the former hardcoded lists
and the club-domain accounts in use) into the production `access_roles`, with one history entry each. Docs: `AGENTS.md`
data rule "roles live only in `access_roles`, never in code"; account tables in `README.md`, `ARCHITECTURE.md` and
`dev/README.md`. Bump `APP_VERSION` and `VERSION`. Deploy order: run the migration → deploy → set
`BOOTSTRAP_ADMIN_EMAIL` once.

### Acceptance criteria

- [ ] Migration script run (dry-run first) against production with the club's approval; every current user listed
- [ ] After deploy, current users keep their access; the bootstrap admin is set and listed
- [ ] Docs and `AGENTS.md` rule updated; version bumped in both files
- [ ] All checks pass as in CI (Python, frontend, OpenAPI contract, e2e)
