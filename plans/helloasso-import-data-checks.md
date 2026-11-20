# Plan: validate and correct HelloAsso membership data at import

> Source PRD: [#135](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/135) (depends on #132 countries, merged, and
> the core of #134 e-mail log, merged as #137/#138).
> Branch: `feat/correct_helloasso_import_issue_135`. At least one commit per phase.

## Architectural decisions

Durable decisions that apply across all phases:

- **Issue**: `{field, code, message, blocking}`. Fields: `birth_date`, `phone`, `emergency_phone_1`,
  `emergency_phone_2`, `email`, `email_2`, `country`, `nationality`, `licence`. `code` is stable (tests, frontend),
  `message` is French. Only `birth_date` issues block.
- **Rules module** (pure domain): one entry point taking the values to check, the season start (1 September of the
  season's first year) and an injected domain check answering yes / no / unknown ("unknown" never gives an issue);
  returns the normalised values and the issues. Plain constants (age 3 to 100), not tied to the group age rules.
- **Blocking birth date**: the record behaves as if its birth date were missing (existing paths: « À vérifier »,
  `can_create` false). Accepted formats: `dd/mm/yyyy` and ISO only.
- **Effective values**: a renewal is checked on the CRM value when filled, else the HelloAsso one; the members
  snapshot carries the checked CRM fields.
- **Writes**: normalised values are stored; a corrected field overwrites the CRM value on a renewal (only exception
  to "fill blank fields only").
- **Preview row** gains `issues`, `corrections` (field → `{value, helloasso_value, author, at}`) and `last_request`
  (`{at, author}` or null).
- **Correction store**: Firestore-only collection `helloasso_membership_corrections`, one document `{season}-{item_id}`,
  per field `{value, helloasso_value, author, at}`; kept after import. Applied right after mapping, before planning,
  in preview and import.
- **Routes** (admin, Firestore-only router, route inventory, OpenAPI + generated types regenerated):
  - `POST /api/helloasso/memberships/corrections/check` — dry run: issues of the submitted values, nothing saved
  - `PUT /api/helloasso/memberships/corrections/{item_id}/{field}` — save, returns the recomputed `MembershipPreview`
  - `DELETE /api/helloasso/memberships/corrections/{item_id}/{field}` — remove, returns the recomputed `MembershipPreview`
  - `POST /api/helloasso/memberships/correction-requests/preview` — the e-mail of the first order, nothing sent (the
    summary is counted by the page)
  - `POST /api/helloasso/memberships/correction-requests` — send, one e-mail per order
- **E-mail log**: new kind `correction_request`; entries gain `helloasso_order_refs` and `helloasso_item_ids`
  (lists). The last request per row: query on `kind`, filtered in Python (no composite index).
- **Import history**: each imported item gains `corrections: [{field, helloasso_value, value}]` (author: the import's).
- **Dependencies**: `phonenumberslite`, `email-validator` (+ `dnspython`), added with `uv add`, requirements
  regenerated. App version bumped.

---

## Phase 1: Birth-date check blocks creation; issues shown on rows

**User stories**: 1, 2, 3, 4, 5, 6

### What to build

The rules module with its birth-date rule; the planner treats a blocking birth date like a missing one; preview rows
carry their issues and the import page lists them under each row.

### Acceptance criteria

- [x] Only `dd/mm/yyyy` and ISO dates are read; `dd/mm/yy` and `dd-mm-yyyy` are unreadable
- [x] Future date, age < 3 or > 100 at season start: blocking issue, row in « À vérifier », cannot create
- [x] Unreadable date: same behaviour as a missing one, with an issue
- [x] Preview rows expose `issues`; the page shows them on the row
- [x] Domain tests at the bounds; planner and API tests

---

## Phase 2: Phones normalised and checked

**User stories**: 7, 8, 9, 10, 11, 12, 13, 26, 48

### What to build

Member phone and both emergency phones checked with `phonenumberslite` (region FR): valid French numbers stored as
`06 12 34 56 78`, foreign ones in international format, invalid or missing member phone flagged as warnings. Renewals
checked on their effective values. Normalised values written on import.

### Acceptance criteria

- [x] `+33 6…`, `0033 6…`, `+33 (0)6…` recognised as French, no warning
- [x] Too short, letters, an e-mail: warning; missing member phone: warning; empty emergency phone: no warning
- [x] A renewal with a filled CRM phone is checked on the CRM phone
- [x] Warnings never block an import; normalised phones are written

---

## Phase 3: E-mails checked

**User stories**: 14, 15, 16, 17, 18

### What to build

Primary and second club e-mails checked with `email-validator` (syntax, normalisation); a domain that cannot receive
mail is flagged through an MX lookup cached per preview, fail-open, disabled in dev and tests.

### Acceptance criteria

- [x] Invalid syntax: warning; missing primary e-mail: warning; empty second e-mail: nothing
- [x] Domain answered "no": warning; "unknown": nothing
- [x] The DNS adapter is injected, faked in tests, off in dev

---

## Phase 4: Countries, nationalities and licence

**User stories**: 19, 20, 22, 23, 24, 25

### What to build

Country and nationality read through `parse_country`: recognised spellings stored canonically without warning,
unknown or missing ones flagged. FFME licence: digits must be exactly 6; a value with no digit counts as empty; a
renewal whose HelloAsso licence differs from the CRM one shows a note that the CRM value is kept.

### Acceptance criteria

- [x] `FRANCAISE`, `france`, `FR` normalised silently; unknown / missing: warning
- [x] Licence of 5 or 7 digits: warning; `non`, `en cours`: empty, no warning
- [x] Renewal licence mismatch: informative note, CRM value kept

---

## Phase 5: Correction dialog and saved corrections

**User stories**: 21, 27, 28, 29, 30, 34, 35 (undo), 36, 37

### What to build

A « Corriger » action opens a dialog with the HelloAsso values, the editable fields and their live issues (dry-run
check route); country and nationality picked from the member form's list. Saving stores the correction, which is
applied before classification on every later preview and on import. Corrected rows show a « corrigée » badge with
the HelloAsso value struck through; a correction can be undone. A corrected field overwrites the CRM value on a
renewal; the import history records the corrections.

### Acceptance criteria

- [x] Check route returns the issues of submitted values without saving
- [x] Save / delete routes return the recomputed preview; corrections survive reloads and syncs
- [x] A correction moving a row (unreadable date → renewal) is classified on the corrected data, in preview and import
- [x] Corrected renewal field overwrites the CRM value; history items list their corrections

---

## Phase 6: Explain section moves

**User stories**: 31, 32, 33, 35 (move on undo)

### What to build

A frontend pure function compares the previews before and after a correction (or its undo): old and new section,
the member now matched, a cancelled choice. The dialog shows it before closing; then the destination section
unfolds and the row is scrolled to and highlighted.

### Acceptance criteria

- [x] Move description tested (Vitest): section change, matched member, cancelled choice, no move
- [x] Dialog announces the move; the row is highlighted in its new section

---

## Phase 7: Send a correction request

**User stories**: 38, 39, 40, 41, 42, 43, 44, 45

### What to build

Rows with problems can be selected and a request sent: one e-mail per order to the payer, primary e-mail in Cc when
valid and different, reply-to the club. A new editable template « Adhésion : informations à corriger » with a
`{problemes}` variable listing, per registration, only the remaining problems with the values as typed. A summary
(e-mails, families, registrations) with an example e-mail comes first. Each send is logged (`correction_request`,
order refs and item ids).

### Acceptance criteria

- [x] `{problemes}` content: grouped by registration, corrected issues left out (domain tests)
- [x] The preview route returns an example; the send route sends one e-mail per order to the payer (+ Cc)
- [x] Each send recorded in the e-mail log with its references

---

## Phase 8: Request trace on rows

**User stories**: 46, 47

### What to build

The preview reads the last `correction_request` per item from the e-mail log; rows show « demandé le … par … »; the
sending dialog warns when a selected registration was already asked.

### Acceptance criteria

- [x] `last_request` on rows from the log
- [x] Warning before sending again for an already asked registration
