# Plan: FFME categories for members and competitors

> Source: grilling session 2026-11-26 (branch `feat/proper_categories`). Related: #173 (forbid adding a competitor
> without a licence for the competition's season — out of scope, assumed here).

Competitors are grouped today by their slot group (`creneau_groupe`, from the HelloAsso tariff), which does not match
the FFME categories they compete in. Each member gets an FFME category, computed from the birth year and the season.

## Decisions

| # | Decision |
|---|---|
| D1 | Rule, keyed on the **season** (1 September switch, as `season_start`), birth **year** only: `age = (season start year + 1) − birth year`. `< 9` → none; 9–10 U11; 11–12 U13; 13–14 U15; 15–16 U17; 17–18 U19; 19–39 SENIOR; 40–49 VETERAN_1; ≥ 50 VETERAN_2. Season 2026-2027: U11 = born 2018–2017 … VETERAN_2 = born 1977 and before |
| D2 | `Category(StrEnum)` in `domain/members/` (like `Sex`): codes `U11 U13 U15 U17 U19 SENIOR VETERAN_1 VETERAN_2`; no category = `""`. Bands in code (ordered table), not in `app_settings`: a FFME change is a commit |
| D3 | One column `users.ffme_category TEXT` (`''`: no category / no birth date). No automatic move-up: members who stay are re-imported, which recomputes |
| D4 | The HelloAsso import computes it **only when it creates a membership** (create / attach / assign without an existing purchase), against the import's season; re-syncs of an existing membership leave it. The admin "add member" form computes it too |
| D5 | Admin-only manual edit through the existing member edit (`POST /api/members/update`), select of the categories + « Aucune », validated against the enum. A save that changes `birth_date` without `ffme_category` recomputes it against the season of the member's latest membership |
| D6 | Participants: the member's category is **copied as is** when added (field `categorie` on the participant row), never refreshed (rare corrections: remove and re-add) |
| D7 | The MyCompet result category `categorie_ffme` goes: results matching no longer writes it; every display uses the participant's `categorie` + sex. The scraper keeps reading category titles (table grouping, `total_categorie`) |
| D8 | Competition list: sections by **category × sex**, age order then F before H, then « Sans catégorie », then « Non identifiés ». One selector (category × sex, every option present in the list, with counts) on phones and computers; on a computer it combines with the registration chips and the search |
| D9 | Members list API: `ffme_category` added, the old `categorie` (slot `categorie_age` / type) removed; CSV « Catégorie » column = FFME category. No new column / filter in the Adhérents table |
| D10 | Migration: one-shot `scripts/migrate_ffme_category.py` (as the former `migrate_gender_to_sex.py`): dry run by default, `--apply` (types the project id), `--emulator`; run in production after the deploy, after a Firestore export; deleted with its test in a later PR |

Labels (frontend only): « U11 » … « U19 », « Sénior », « Vétéran 1 », « Vétéran 2 »; with the sex: « U13 F ».

## Architectural decisions

- **Schema**: `users.ffme_category TEXT` (SQLite cache, `_add_missing_column`), replicated as `crm_users.ffme_category`;
  Firestore `adherents/{id}.ffme_category`; participant rows of `competitions/{id}`: `categorie` added, `categorie_ffme` removed
- **API**: `MemberRow.ffme_category` (members list), `MemberUpdate.fields.ffme_category` (admin), `CompetitionMember.ffme_category`,
  `Participant.categorie`; `categorie` (members list) and `categorie_ffme` (participants) removed. Regenerate `openapi.json` and `api-schema.ts`
- **Roles**: unchanged (member edit is admin, competitions coach-writable)
- **Version**: bump `APP_VERSION` and `VERSION` in the first phase that changes behaviour (one bump for the branch)

---

## Phase 1: Category rule, shown on members

**User stories**: rule for every season; category visible in the member details; members list and CSV

### What to build

The pure category function (birth date + season → category or none) with its enum, the `users.ffme_category` column,
its exposure in the members list API (replacing the old `categorie`), the category in the member details next to sex
and age, and the CSV « Catégorie » column. The emulator seed gives members categories so it can be seen in dev.

### Acceptance criteria

- [x] The rule gives the examples of D1 for 2026-2027, and the shifted ones for another season; < 9 and missing birth date → none
- [x] `ffme_category` is added to existing caches at startup and replicated to Firestore
- [x] The members list returns `ffme_category`; `categorie` is gone from API, TS types and CSV
- [x] Member details show the category label; the Adhérents CSV « Catégorie » holds it
- [x] Seeded emulator members have categories

---

## Phase 2: Computed when a membership is created

**User stories**: category computed at the HelloAsso import

### What to build

The HelloAsso import writes the member's category when it creates a membership (new member, member completed,
registration assigned without an existing membership), against the import's season. Re-syncing an existing membership
(update, backfill, assign over a manual membership) does not touch it. The admin "add member" form computes it for the
chosen season.

### Acceptance criteria

- [x] Importing a new registration sets the category of that season
- [x] A renewal (new season's membership for an existing member) recomputes it, overriding a manual value
- [x] Updating an existing membership leaves a manual value untouched
- [x] Adding a member by hand sets it

---

## Phase 3: Manual correction

**User stories**: category can be updated manually; birth date fix

### What to build

The admin member edit form gets a category select (the categories + « Aucune »). The server accepts only enum values.
A save that changes the birth date without sending a category recomputes it against the season of the member's latest
membership; a save sending both keeps the admin's category.

### Acceptance criteria

- [x] An admin can set and clear the category; an unknown value is refused (422)
- [x] Changing only the birth date recomputes the category; changing both keeps the one sent
- [x] Non-admins cannot change it (existing role of the route)

---

## Phase 4: Category copied onto participants and shown everywhere

**User stories**: competitors carry their category; `categorie_ffme` removed

### What to build

The `adherents` directory carries `ffme_category`. Adding a competitor (form, « Charger le groupe », HelloAsso link and
webhook) copies it into the participant's `categorie`. Results matching stops writing `categorie_ffme`. Participant
rows, cards, the balance, the contact dialog, the results e-mail and the Excel/PDF competitor exports show
`categorie` + sex.

### Acceptance criteria

- [x] A newly added participant has the member's category; later member changes do not alter it
- [x] `categorie_ffme` is no longer written nor read (API, model, UI, exports, e-mail)
- [x] Every competitor display shows « U13 F »-style labels, nothing when no category

---

## Phase 5: Competition list by category × sex

**User stories**: competitors grouped by category instead of schedule group

### What to build

The competition detail lists competitors in category × sex sections (age order, F before H, « Sans catégorie »,
« Non identifiés »). One selector, the same on phone and computer, lists every category × sex present with its count;
on a computer it combines with the chips and the search. The participants CSV has « Catégorie » instead of « Créneau ».
The slot group remains only in the contact dialog.

### Acceptance criteria

- [x] Sections and their order as above, names sorted inside
- [x] The selector shows on both layouts, combines with the chips and search on a computer, lists options without selected competitors
- [x] The count line reflects the selector and the chip
- [x] The participants CSV « Catégorie » column

---

## Phase 6: Migration script

**User stories**: migration of the members already imported

### What to build

`scripts/migrate_ffme_category.py` against Firestore: fills `crm_users.ffme_category` (season of each member's latest
membership) where the field is absent; adds `categorie` to participants without one, computed against the
competition's season (from its date), and removes `categorie_ffme`; refreshes the `adherents` directory. Dry run report
(counts per category, members not computed by user id, no names), `--apply` with project id confirmation, `--emulator`.
Re-runnable.

### Acceptance criteria

- [x] Dry run writes nothing and reports counts
- [x] `--apply` fills users and participants as above; a second run changes nothing
- [x] A user already holding `ffme_category` (edited since) is left alone
- [x] Tested against the emulator store / a fake store, as the former gender migration
