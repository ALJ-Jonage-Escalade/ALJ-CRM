# Plan — unlimited emergency contacts

Replace the four fixed `users` columns (`emergency1_name`, `emergency1_phone`, `emergency2_name`, `emergency2_phone`) with an
ordered list of contacts per member, in a new `emergency_contacts` table (Firestore `crm_emergency_contacts`, SQLite cache).
Two releases: release A moves every read and write to the table, release B removes the old columns and fields.

## Decisions (grilling session, 2026-11-05)

| # | Decision |
|---|---|
| D1 | **One owner per contact**: `id`, `user_id`, `name`, `phone`, `position`, timestamps. Siblings keep separate copies; no shared contacts and no link table. No "relationship" field. No limit on the number of contacts |
| D2 | **HelloAsso import adds what is missing**: a contact is added unless the member already has it (D3); existing rows are never changed. A contact deleted by an admin returns if a later registration includes it (accepted) |
| D3 | **What counts as the same contact**: same phone digits (`+33` / `0033` read as `0`); without a phone, same name (`normalize_name`). One domain function, used by the import and the migration |
| D4 | **API**: an ordered `emergency_contacts: [{name, phone}]` on the member, in reads and writes. Sending it replaces the list in the member's transaction; leaving it out changes nothing. No new route, same admin role. Two admins editing at once: the last save wins (accepted) |
| D5 | **Validation**: a row needs a name or a phone; fully blank rows are dropped on save and at migration; phone format is checked in the form when a phone is present, as today |
| D6 | **The participant copy stays**: `urgence_nom` / `urgence_tel` and the `adherents` fields `emergency_name` / `emergency_phone` keep their names and are filled from the first contact. Stored competitions are not rewritten. The copy is used only when the phone has no competitor entry for that athlete |
| D7 | **The first contact is the main one**: it feeds the FFME export and the participant copy. The form offers add, remove and up/down arrows, and labels the first row « Principal » |
| D8 | **Rollout**: export → copy → release A → copy again → check → release B → delete the old fields. No read fallback to the old columns on the server |
| D9 | **Offline**: no phone may lose emergency numbers because of the migration (see below) |

### Offline compatibility (D9)

Two cases, both handled only until release B unless noted:

- **New app, old saved data**: the IndexedDB copies of `competitors` and of the directory still hold the flat fields. One frontend
  helper reads either format, so these copies keep working offline.
- **Old app, new API**: a tab opened before the deploy keeps running its build and keeps polling (`sw.ts`: the API is network only),
  and a reload while offline can serve the old precached build. So in release A, member reads (`Member`, `CompetitorContact`) also
  return `emergency1_*` / `emergency2_*`, derived from the first two contacts. Release B removes them.

An old tab that saves a member gets a 422, because `RequestBody` forbids unknown fields: a visible error, not a silent loss. Reloading fixes it.

---

# Release A — the table becomes the source

## Phase 1 — Domain

- New module `src/domain/members/emergency_contacts.py` (`from __future__ import annotations`, typed, added to `[tool.mypy] files`):
  - `EmergencyContact` (name, phone)
  - `clean_contacts(rows)`: strips values, drops blank rows
  - `same_contact(a, b)` (D3) and `missing_contacts(existing, incoming)`, which keeps the order and also removes duplicates within `incoming`
- `Member` (`domain/members/models.py:46`): replace the four fields with `emergency_contacts`. Check what `from_dict` / `to_dict` still need
  for the `champ_…` labels (`domain/constants.py:67`), which remain HelloAsso's input keys
- Tests `tests/domain/members/test_emergency_contacts.py`: parametrized phone spellings, name-only rows, blank rows, order kept;
  update `tests/domain/members/test_member_v2_adapter.py`

## Phase 2 — Cache and sync

- `infrastructure/sqlite/schema_v2.py`: `emergency_contacts` table in `V2_DDL`, indexed on `(user_id, position)`
- `infrastructure/firestore/cloud_sync/common.py`:
  - add the table to `TRACKED_TABLES`
  - add `("emergency_contacts", "user_id")` to `REFERENCES["users"]`; **without it, a renumbered member leaves their contacts on another member's id**
  - bump `CACHE_FORMAT` to `"3"`, so caches are rebuilt from Firestore
  - a tombstone of this table keeps `user_id` (`TOMBSTONE_FIELDS`, no name or phone): tombstones otherwise hold only their key, and the
    migration needs to know whose contacts were removed (phase 7)
- The `users` columns stay in this release, unread and unwritten, so a rollback finds them
- Tests: a renumbered user keeps their contacts (`renumber_row`); a contact created, edited and deleted syncs, tombstone included

## Phase 3 — Repository, reads and writes

- `infrastructure/sqlite/members.py`:
  - `_MEMBER_ROWS_SQL` (`:88`) no longer selects the four columns; `list_member_rows` and `list_member_rows_of_users` load the contacts in
    one extra query, grouped by user (no query per member)
  - `replace_emergency_contacts(cur, user_id, contacts, now_iso)`: updates rows in place by position, inserts the extra ones, deletes the
    surplus. Unchanged rows are not rewritten, so sync sends only what changed
  - `update_member_fields` (`:507`) and `add_manual_member` (`:279`) use it, in their existing transaction
- `schema_v2.py`:
  - remove the four entries from `USER_FIELD_MAP` (`:131`) and the two from `IHM_TO_USERS` (`:183`)
  - `v_adherents_legacy` (`:679`): `emergency1_*` come from the contact at the lowest position, and `emergency2_*` are removed if no reader remains
- Import (D2): `upsert_user_v2` and `fill_blank_user_fields` (used for new and returning members) add missing contacts from the two HelloAsso
  fields, through `missing_contacts`
- `domain/members/view.py:164`: format each contact (`fmt_first_name`, `fmt_phone`); `COMPETITOR_FIELDS` (`:196`) returns the list and the temporary flat fields
- `infrastructure/firestore/competitions/adherents.py:124`: the projection takes the first contact (D6); `participants.py:102` is unchanged
- Tests:
  - import: new number added, same number in another spelling not added, existing row unchanged, a form's second contact added
  - replace: reorder, shrink to empty, grow past two
  - projection: first contact copied

## Phase 4 — FFME export

- `exports/membership_excel.py:215,226` reads the first contact, through the view or the list
- `tests/exports/test_ffme_golden_master.py` must stay byte-identical. **A member with a blank contact 1 and a filled contact 2 now exports
  contact 2 as main**, so check the fixture. If its output changes, the club approves the new reference before merging
- Test: the first contact by position is the one exported, after a reorder

## Phase 5 — API contract

- `api/members/schemas.py`:
  - new `EmergencyContact` model (`name: str = ""`, `phone: str = ""`)
  - `Member` (`:53`) and `CompetitorContact` (`:91`): add `emergency_contacts`, keep the flat fields, described as deprecated
  - `MemberChanges` (`:139`): `emergency_contacts: Optional[List[EmergencyContact]] = None`, flat fields removed
  - `NewMember` (`:184`): `emergency_contacts: List[EmergencyContact] = []`, flat fields removed
- Regenerate: `uv run python dev/export_openapi.py`, then `npm run gen:api` in `frontend/`; commit `openapi.json` and `src/lib/api-schema.ts`
- Tests (`tests/api/members/test_members.py`, `test_competitors.py`, `tests/web/test_bureau_web.py`): list saved in order, list left out
  changes nothing, `[]` empties it, blank rows dropped, a flat field in a write → 422, a non-admin write refused, flat read fields match the list.
  `tests/test_route_inventory.py` is unchanged (no new route)

## Phase 6 — Frontend

- Offline reader (D9): `emergencyContactsOf(record)` in `src/lib/`, returning the list or else the flat fields of an old copy, with a type guard
  rather than an `as` cast. Unit test for both formats
- Member form (`adherents/MemberForm.vue:255`, `adherents/record.ts`):
  - a list of rows, each with name, phone, ↑, ↓, 🗑; `➕ Ajouter un contact` below; the first row labelled « Principal », the next « Contact 2 »…
  - `MemberDraft` holds the list; `draftErrors` reports errors per row (`Numéro de téléphone invalide.`) and shows them under the right row
  - stable row identity in the draft (a local key), so moving a row keeps focus and values
  - ↑ absent on the first row, ↓ absent on the last; buttons have an `aria-label` and work with the keyboard
- Displays, one line or card per contact, `🚨 Urgence N`:
  - `adherents/record.ts:38`
  - `annuaire/directory.ts:25,73,90` (`FIELDS` keeps `emergency_contacts`)
  - `DirectoryPage.vue:377`
  - `competitions/competitions.ts`: `ContactCard.role` becomes `"athlete" | "emergency"`; `athleteContactCards` and `participantRows` share one
    helper: the competitor entry's list when there is an entry, else the copy (D6)
  - `competitions/detail/ParticipantCard.vue:111`: key by position, since two rows may share a phone
  - `competitions/detail/AthleteContactDialog.vue`: the cards are keyed so any number renders
- Fixtures and tests: `members.fixture.ts`, `record.test.ts`, `MemberForm.test.ts`, `directory.test.ts`, `DirectoryPage.test.ts`, `competitions.test.ts`,
  `CompetitionsPage.test.ts`, including an offline test with a copy in the old format and a member with three contacts
- `npm run format && npm run lint && npm run typecheck && npm test`

## Phase 7 — Migration script

`scripts/migrate_emergency_contacts.py`, kept in the repo and modelled on `scripts/migrate_gender_to_sex.py`: dry run by default, `--apply` asks to
type the project id, `--emulator` for dev. It runs before release A is deployed: the current code ignores the new collection.

- For each `crm_users` document: contact 1 then contact 2, cleaned and de-duplicated (D3, D5); `position` 0, 1; ids from `max_int_id + 1`;
  `_modified_at` set so instances pull them
- **Skips a member who has any document in the collection, tombstones included**, so a second run cannot restore contacts an admin has
  just removed. Writes with a "must not exist" precondition; on a conflict (an instance took the id) it re-reads the max id and retries
- Never writes to `crm_users` in this mode
- Report, by user id and order ref (no names, no phones):
  - counts of members with 0, 1 and 2 contacts, and of duplicates dropped
  - **members with a blank contact 1 and a filled contact 2** (their FFME export changes)
  - **members whose rows differ from the old columns** (edits made between the copy and the deploy, to fix by hand)
- `dev/seed/seed_emulator.py`: seeds contacts in the new form (including a member with three) once the columns are unread
- Tests against the fake Firestore: migrates, re-runs without change, skips tombstones, drops the duplicate, id conflict retried

## Phase 8 — Release A

- Bump `APP_VERSION` (`src/domain/constants.py`) and `code_source/VERSION`
- All checks: `uv lock --check && uv run python dev/export_requirements.py --check && uv run ruff check src tests && uv run mypy && uv run pytest tests`,
  `uv run python dev/export_openapi.py --check`, frontend checks, e2e including `e2e/test_offline.py` (`-n 1` locally)
- Production rollout (ask before each step):
  1. Firestore export (backup)
  2. Script dry run, review the report, then `--apply`
  3. `./scripts/deploy_cloud_run.sh --test`, check on the test URL. It uses production data: no contact edits there
  4. `./scripts/deploy_cloud_run.sh` (100 %)
  5. Script again, at once: fills members with no rows and reports the differences; fix those by hand
  6. Check in production: a member with two contacts, a competition card, the FFME export, a phone going offline
- Keep contact edits to a minimum between steps 2 and 5. **Rollback after step 4** (`--rollback`) brings back the old columns, without the contact edits made since the deploy

---

# Release B — remove the old columns and fields

Deploy only after release A has been checked in production. Nothing here is undoable without the export from this release's first step.

## Phase 9 — Code

- `schema_v2.py`: remove the four columns from `users`, and the `emergency1_*` of the view if the export no longer needs them
- Bump `CACHE_FORMAT` to `"4"`. Sync ignores Firestore fields with no matching column (`sync.py`, `bootstrap.py`), so instances keep working
  until the fields are deleted
- API: remove the flat read fields from `Member` and `CompetitorContact`, and `COMPETITOR_FIELDS`; regenerate the contract
- Keep `emergency1_*` reading in `emergencyContactsOf`: phones may still hold old copies. Remove it in a later release, as a separate decision
- Update the tests that asserted the temporary fields; bump the versions

## Phase 10 — Delete the fields

- Add `--delete-legacy` to the script: removes the four fields from `crm_users`, like the `gender` deletion; dry run first
  - It stops if a member has values in the old fields but no document in the collection (never migrated). Differences from the old fields are
    expected by now, since admins have edited contacts since release A, so they don't block it
- Rollout (ask before each step):
  1. Firestore export: the only way back after step 3
  2. Deploy release B (`--test`, then production)
  3. Dry run, review, `--delete-legacy --apply`
  4. Check a member, a competition and the FFME export again

## Out of scope

- A relationship field, sharing contacts between siblings
- Refreshing or removing the participant copy
- **To check separately**: the `Competition` response model includes `urgence_nom` / `urgence_tel`, and read-only accounts can open competitions while
  only the screen hides these values (`contactsShown`). Confirm against a running server whether the API sends them to those accounts. Existing behaviour, unchanged by this plan
