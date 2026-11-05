# Plan: Import members from the HelloAsso membership campaign

> Source PRD: https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/70

## Architectural decisions

Durable decisions that apply across all phases:

- **Routes** (members theme, admin role only, Pydantic `response_model`, standard error responses, listed in the route inventory):
  - `POST /api/helloasso/memberships/preview` — no body; uses the active season → campaign, season, guard status, bucket counts, rows per bucket
  - `POST /api/helloasso/memberships/import` — `{season, decisions: {item_id: decision}}` → applied counts, created / renewed / updated member ids, history id
  - The server always recomputes the plan on import; the browser only sends decisions keyed by HelloAsso item id, never member data
  - Errors: missing credentials / HelloAsso unreachable → explicit error; season guard failure → 409 with the reason; stale or unknown decisions → 409
- **Buckets**: `already_imported`, `new`, `renewal`, `updated`, `to_review`, `blocked` — every item lands in exactly one, with a reason
- **Decisions**: unchecked row = skip; `to_review` rows take `link:<member id>` / `create` / `skip` (default `skip`)
- **Schema** (SQLite v2 cache, replicated to Firestore like the other purchase columns): new nullable columns on `purchases`:
  `helloasso_item_id` (unique when present), `helloasso_status`, `helloasso_amount`, `helloasso_tarif` (last values seen from HelloAsso)
- **Identity**: normalised last name + first name + birth date (`normalize_name` helpers); FFME licence is a second identity key, never a duplicate signal
- **Campaign**: the `HELLOASSO_MEMBERSHIP_CAMPAIGN` setting chosen in Paramètres › Campagnes (#81) → `CAMPAIGN_SLUG` env var → default slug pattern for the active season (`MembershipImportService.campaign_reference()`, shared with the dashboard). The Paramètres setting first built here was removed in favour of that page. The sync page's select starts on that campaign; picking another one previews and imports it for that sync only (sent as `campaign` to preview and import, recorded in the history, never saved)
- **Import history**: Firestore collection, one document per import (who, when, season, campaign, counts per bucket, item ids with their decision)
- **Layering**: pure domain modules (item mapper, import planner, decisions applier) ↔ thin service ↔ SQLite repository (writes go through the existing replicated repository path, season always passed explicitly) ↔ router ↔ frontend service in `src/services/` ↔ Outils card
- **Side effects**: the import sends no e-mail and never deletes or deactivates members
- **Contract**: after each route/model change, regenerate `frontend/openapi.json` and `src/lib/api-schema.ts`
- **Versioning**: bump `APP_VERSION` and `VERSION` together in every phase that changes behaviour
- **Offline**: the Outils card is disabled with an explanation when offline (hard constraint)

---

## Phase 1: Campaign setting and read-only preview

**User stories**: 2, 3, 4, 9, 24, 25, 33, 35, 36, 37, 41

### What to build

An admin sets the membership campaign in Paramètres. On the Outils page, a new "Synchroniser les adhésions HelloAsso" card opens a preview: the server resolves the campaign, checks it against the active season, fetches the campaign items from HelloAsso, maps each one into a flat membership record (custom fields read from both `answer` and `value`, birth date parsed, licence digits only) and classifies them. In this phase every item is either `new` or `blocked` (with its reason); a season mismatch blocks the whole plan. The preview shows campaign, season, bucket counters and rows per bucket. Nothing is written. Missing credentials and HelloAsso failures surface as explicit errors; the card is disabled offline; coaches and read-only users neither see nor can call it.

### Acceptance criteria

- [x] `HELLOASSO_MEMBERSHIP_CAMPAIGN` is editable in Paramètres › Campagnes (#81); the campaign resolves setting → env var → default pattern
- [ ] A campaign whose slug does not match the active season's years blocks the whole preview with a reason
- [ ] The item mapper is a pure, shared module, tested with parametrized tables (incl. `answer` vs `value`, unparseable birth date)
- [ ] The preview route returns counters and rows; no SQLite or Firestore write happens
- [ ] Missing credentials / unreachable HelloAsso return an explicit error shown on the card
- [ ] The route is admin-only (coach and read-only refused), in the route inventory, and the OpenAPI contract is regenerated
- [ ] The card is hidden for non-admins and disabled with an explanation offline (Vitest)

---

## Phase 2: Import new members

**User stories**: 1, 16, 18, 23, 26, 27, 28, 29, 38, 39

### What to build

The preview rows get pre-checked checkboxes. On confirm, the browser sends the season and the per-item decisions; the server re-reads HelloAsso, recomputes the plan, applies the decisions (rejecting decisions for unknown items or rows whose bucket changed) and writes in one transaction: user, order, purchase (with the new HelloAsso columns filled), options, amounts, tariff (waiting-list tariffs keep their name) and every HelloAsso status. Slot groups follow from the tariff as they already do. A result screen lists the created members with links to their record. No e-mail is sent.

### Acceptance criteria

- [ ] The `purchases` schema migration adds the four HelloAsso columns, with `helloasso_item_id` unique when present
- [ ] The decisions applier is pure and tested: unchecked rows skipped, unknown / stale decisions rejected
- [ ] Import creates members, orders, purchases and options in one transaction through the replicated repository path
- [ ] All HelloAsso statuses are imported; amounts and insurance options are stored per registration
- [ ] Unchecking a row in the preview excludes it from the import
- [ ] Result screen lists created members with links to their record
- [ ] No e-mail is sent (asserted in the API test)
- [ ] API round trip preview → import tested with HelloAsso mocked; contract regenerated; version bumped

---

## Phase 3: Re-runs and renewals

**User stories**: 5, 6, 7, 8, 14, 17, 22

### What to build

Running the import again is safe, and returning members are recognised. Items whose HelloAsso item id is already stored are `already_imported`; legacy purchases without item id match on order reference + person and get the item id back-filled. Known people (same name + birth date, or same FFME licence) become `renewal`: the new season's membership is attached to the existing member and only blank personal fields are filled. A registration without usable birth date is a renewal only when its licence matches exactly one member. The existing purchase priority score decides which membership counts when a person has several.

### Acceptance criteria

- [ ] Running the import twice creates no duplicate member, order or purchase
- [ ] Legacy purchases without item id are recognised and back-filled
- [ ] Renewal by name + birth date and by licence both attach the season to the existing member
- [ ] A known licence never yields "duplicate" or a dropped row
- [ ] Missing birth date + unique licence match → renewal
- [ ] Existing non-empty personal fields are never overwritten (repository test)
- [ ] Priority between several registrations of one person follows the existing score (planner table test)
- [ ] Result screen lists renewed members

---

## Phase 4: "À vérifier" bucket

**User stories**: 10, 11, 12, 13, 15

### What to build

Ambiguous identities go to `to_review` instead of being guessed: licence matches but name differs, name matches but birth date differs, several candidates, or missing birth date without a unique licence match (never created as `new`). A name close to a member born the same day (same last name, same first name, or the two swapped: a typo or a field mix-up) also goes to `to_review` with that member as candidate, instead of `new`. Each row lists candidate members and offers link to a candidate / create new / skip, defaulting to skip. The applier honours the choice on import.

### Acceptance criteria

- [ ] Each conflict case lands in `to_review` with candidates (planner table test)
- [ ] Missing birth date without unique licence match is never `new`
- [ ] The UI requires an explicit choice per row and defaults to skip (Vitest)
- [ ] `link:<member id>` attaches to that member; `create` creates a new one; `skip` writes nothing
- [ ] A link to a member id that is not a candidate is rejected

---

## Phase 5: Changes on HelloAsso

**User stories**: 19, 20, 21

### What to build

Later syncs detect refunds, cancellations, waiting-list promotions and tariff/amount changes. An already imported item whose HelloAsso status, amount or tariff differs from the last values recorded becomes `updated`, shown old → new and pre-checked; accepting it updates the purchase and the recorded HelloAsso values. A value changed only in the CRM is never proposed. When both HelloAsso and the CRM changed, the row goes to `to_review`, unchecked, showing the CRM value and the HelloAsso value.

### Acceptance criteria

- [ ] HelloAsso-only change → `updated` with old → new values
- [ ] CRM-only change → stays `already_imported`, nothing proposed
- [ ] Both changed → `to_review`, unchecked, both values shown
- [ ] Accepting an update writes the purchase values and the last-seen HelloAsso values
- [ ] Result screen lists updated members

---

## Phase 6: Traceability

**User stories**: 30, 31, 32

### What to build

Every import writes one Firestore history document (who, when, season, campaign, counts per bucket, item ids with their decision) and appends "Import HelloAsso du JJ/MM" to the comment of each written purchase without losing existing comments. The Outils card shows "Dernière synchro : date, par X" from the latest history entry.

### Acceptance criteria

- [ ] One history document per import, returned as history id by the import route (fake Firestore test)
- [ ] The marker is appended to existing comments, never replacing them
- [ ] The card shows the last sync date and author, and an empty state before the first import

---

## Phase 7: Dashboard alignment and legacy cleanup

**User stories**: 34, 40

### What to build

The membership dashboard reads the same campaign setting and uses the shared item mapper (keeping its own geocoding and aggregation), so the dashboard and the import never disagree. The orphaned desktop pipeline (old HelloAsso fetch, Google Drive helpers, environment loader) and its test are removed; the FFME CSV export and its golden master stay untouched.

### Acceptance criteria

- [ ] The dashboard resolves the campaign through the shared setting resolution
- [ ] The dashboard's records come from the shared mapper; existing dashboard behaviour unchanged
- [ ] The legacy pipeline and its test are gone; nothing else imports them
- [ ] The FFME golden master test passes byte-identical

---

## Phase 8: End-to-end scenario

**User stories**: 1, 2, 12, 23, 27 (verification)

### What to build

A Playwright scenario against the existing fake HelloAsso server covering the full flow: open the Outils card, run the preview, uncheck a row, resolve a `to_review` row, confirm, then find the imported member in Adhérents. The fake server gains the membership campaign items it needs.

### Acceptance criteria

- [ ] The fake HelloAsso serves a membership campaign with new, renewal and to-review cases (fake data only)
- [ ] The scenario passes locally (`-n 1`) and in CI
- [ ] The imported member is visible in Adhérents; the unchecked row is not imported

---

## Phase 9: Attach a registration to any member

**Case**: a parent registers a child under the parent's own name: HelloAsso says "WEASLEY Molly", the membership is Ginny's.
The matcher sees Molly (new, or a renewal of Molly herself when she is a member).

### What to build

A manual decision `attach:<member id>`: the admin attaches a registration to any member of the base, with a required
comment. The member is created by hand first when needed (Adhérents). No mapping table: the link is
`purchases.helloasso_item_id`, so later imports recognise the item by its id.

- **Where**: the preview, on the `new` and `renewal` rows ("🔗 Rattacher…" next to the checkbox) and the `to_review`
  identity rows (an option of the select)
- **Takeover**: a non-HelloAsso membership of the member this season (e.g. the `MANUEL-…` order of `members/create`)
  is taken over: the HelloAsso values (order, status, amount, tarif, insurance options) replace the manual ones; the
  comment and group/slot are kept. Several non-HelloAsso memberships this season: refused. None: a membership is added
- **Member record**: nothing copied from HelloAsso (its data are the parent's); `link:` keeps filling the blank fields
- **Comment**: required; appended to the membership comment as `[dd/mm/yyyy] <comment>`, followed by an automatic line
  (HelloAsso name, order, author); kept in the import history with the decision
- **Refused** (in the preview and again on import, `stale_decisions`): a member who already has a HelloAsso membership
  this season, or a member chosen for two registrations of one import
- **Member search**: every member of the base (any season), from a light list added to the preview answer (id, names,
  birth date, licence, membership this season); accent-insensitive search in the page
- **Checkboxes in "À vérifier"**: every writable row has a checkbox; the select starts on "— Choisir… —" (no "Ignorer"
  option: unchecked = skipped); picking an option checks the row; unchecking keeps the choice. An attach counts only
  once a member and a comment are given; "Importer" is disabled while a checked row is incomplete
- **Later imports**: an imported row whose member has another name shows "HelloAsso name → member" (link to the record)
- **Confirmation**: the dialog lists each attachment ("WEASLEY Molly (commande 12345) → WEASLEY Ginny, née le …")
- **Out of scope**: undoing an attach (#84)

### Acceptance criteria

- [x] `attach:<id>` takes over the member's manual membership of the season, or adds one; nothing written on the member
- [x] The comment and the automatic line are appended to the membership comment, the comment kept in the history
- [x] Attaching to a member already holding a HelloAsso membership this season, or twice in one import, is refused
- [x] The next preview shows the item as already imported, "HelloAsso name → member"
- [x] "À vérifier" rows have a checkbox, checked when a choice is made; an incomplete attach blocks the import
