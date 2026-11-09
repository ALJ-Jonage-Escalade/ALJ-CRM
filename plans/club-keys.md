# Plan: Club keys (HID ProxKey) management

> Source: design interview (grilling) of 2026-11-09 — replaces the HID ProxKey fields of the member card.

## Architectural decisions

Durable decisions that apply across all phases:

- **Page**: Outils sub-page « 🔑 Clés », id `cles`, path `/bureau/outils/cles`, `access: "staff"`, `offline: "none"`
  (online only, as every Outils sub-page). Coaches read; every write is admin only (server-enforced, the buttons
  hidden for coaches).
- **Routes** (server theme `keys`, front service `src/services/keys.ts`):
  - `GET /api/keys` — every key with its status, current holder and the « not a member this season » flag
  - `POST /api/keys` `{code}` — add a key (admin)
  - `PATCH /api/keys/{key_id}` `{code}` — rename (admin, `renamed` event)
  - `GET /api/keys/{key_id}/history` — assignments and events, chronological
  - `POST /api/keys/{key_id}/assignments` `{user_id, given_on, comment}` — assign (admin)
  - `POST /api/keys/{key_id}/return` `{returned_on, comment}` — close the open assignment (admin)
  - `PATCH /api/key-assignments/{assignment_id}` `{given_on, returned_on, comment}` — correct (admin)
  - `DELETE /api/key-assignments/{assignment_id}` — only the key's most recent one (admin, `assignment_deleted` event)
  - `POST /api/keys/{key_id}/archive` `{archived_on, comment}` — comment required; closes the open assignment (admin)
  - `POST /api/keys/{key_id}/restore` `{comment}` — back to available (admin)
- **Schema** (SQLite cache, replicated to Firestore: in `TRACKED_TABLES`, ids renumbered through `REFERENCES`):
  - `keys(id, code, status, created_at, updated_at)` — `code` free text, trimmed, unique case-insensitive, archived
    keys included; `status` ∈ `available | assigned | archived`
  - `key_assignments(id, key_id, user_id, given_on, returned_on, comment, return_comment, by, created_at)` —
    `returned_on` NULL while held; at most one open assignment per key and per user (partial unique indexes)
  - `key_events(id, key_id, type, date, comment, by, created_at)` — `type` ∈ `archived | restored | renamed |
    assignment_deleted`
  - `by`: e-mail of the admin who acted
- **Rules**: only members of the active season can be given a key; an archived key cannot be assigned; restoring
  never reopens an assignment; no automatic action when a holder does not renew (only the ⚠️ flag).
- **No data migration**: the single key recorded today is re-entered by hand; the `users.hid_proxkey*` columns are
  dropped in phase 5 (data loss accepted by the owner).
- **Concurrency**: ~5 users, a single instance in practice — SQLite constraints and a server transaction, nothing more.

---

## Phase 1: Key list and adding keys

**User stories**: view the club keys; add a key; coaches read, admins write.

### What to build

The three tables, registered in the Firestore replication. The « 🔑 Clés » Outils sub-page: a table (Code, Status,
Holder, Given on, Comment), natural sort by code, text search, counters (assigned / available / archived), and an
« + Ajouter une clé » button for admins only.

### Acceptance criteria

- [ ] `POST /api/keys` creates an available key; a duplicate code (case-insensitive, trimmed) → 409; empty → 422
- [ ] A coach can `GET /api/keys` but gets 403 on `POST`
- [ ] The tables are tracked by the replication (`TRACKED_TABLES`, `REFERENCES`)
- [ ] The sub-page lists keys sorted naturally (2 before 10), filters on the search, shows the counters; the add
      button only shows for admins

---

## Phase 2: Assign and return

**User stories**: link a key to a member; one key per person; spot holders who did not renew.

### What to build

From a key, an admin assigns it to an active-season member who holds no key (others shown greyed out « détient déjà
n° X »), date defaulting to today, optional comment; and records its return (date ≥ given date, optional comment).
The holder links to the member's record in Adhérents; ⚠️ and an « ⚠️ uniquement » filter mark holders without a
membership in the active season.

### Acceptance criteria

- [ ] Assigning an assigned or archived key, or a member who holds a key, or a member not in the active season → 409
- [ ] Return closes the open assignment, the key becomes available; returned_on < given_on → 400
- [ ] `GET /api/keys` returns the holder (id, name), given_on, comment, the not-renewed flag and the season of
      their record (active one, else their last one: the link opens it)
- [ ] Page: assign / return dialogs, holder link, ⚠️ filter

---

## Phase 3: History panel and corrections

**User stories**: keep the history of who held which key when; fix mistakes.

### What to build

Clicking a key opens a side panel with its chronological history (assignments with from/to, comments, admin;
events with date, comment, admin) and the admin actions. Admins can edit an assignment's dates and comment, delete
the key's most recent assignment (recorded as an `assignment_deleted` event), and rename the key (`renamed` event,
old → new).

### Acceptance criteria

- [ ] `GET /api/keys/{id}/history` returns assignments and events in date order
- [ ] Editing respects given_on ≤ returned_on; deleting an older assignment → 409
- [ ] Rename keeps uniqueness (409) and writes the event
- [ ] Panel shows the history and the actions (admins only)

---

## Phase 4: Archive and restore

**User stories**: archive (not delete) a lost key with a comment; undo an archive.

### What to build

Archive asks for a required comment and a date (today by default); in one transaction it closes the open assignment
at that date and archives the key. Restore asks for an optional comment and makes the key available. Archived keys
are hidden from the table, behind « 🗂 Afficher les archives (N) » / « 🙈 Masquer les archives », as on the
Competitions list (separate greyed list, archive date and comment shown).

### Acceptance criteria

- [ ] Archive without comment → 422; archiving an archived key / restoring a non-archived key → 409
- [ ] Archiving an assigned key closes its assignment at the archive date
- [ ] An archived key cannot be assigned (phase 2 rule, tested here)
- [ ] Page: archive / restore dialogs, archives toggle

---

## Phase 5: Member side and removal of the old fields

**User stories**: declutter the member card; see a member's key from their record.

### What to build

The member payload gains the current key (`{id, code, given_on}` or null); the record view shows « 🔑 Clé n° X depuis
le … », linking to the key on the Clés page. The member card key section, the 🔑 « Diplômes » badge and its sort
weight, the CSV export key columns, and the `hid_proxkey*` fields (API schemas, `users` DDL, column migrations,
field map) are removed; existing caches lose the columns.

### Acceptance criteria

- [ ] No `hid_proxkey` left in `src/` nor `frontend/src/` (outside generated files, regenerated)
- [ ] Record view shows the current key with its link, nothing for a member without one
- [ ] Existing caches no longer carry the columns after startup
- [ ] All checks green (back + front, OpenAPI contract)
