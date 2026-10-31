# Plan: Paramètres › Campagne HelloAsso (list and choose the active campaigns)

> Branch: `feat/configure_campaign`. Design settled by a grilling session (2026-10-31).
> Follow-up kept out of scope: the unused per-competition `helloasso_ref` field,
> [#80](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/80).

The app uses two HelloAsso campaigns, both set by hand-typed slugs:

- **membership**: `CAMPAIGN_SLUG` (env / Cloud Run variable through `SecretStore`), read by `/api/dashboard`;
  it can't be changed from the UI;
- **competitions**: `HELLOASSO_ANNUAL_CAMPAIGN` (Firestore `app_settings`), read by `POST /api/helloasso/sync` and the
  webhook; no screen sets it.

A new Paramètres sub-page lists the club's HelloAsso campaigns per type, with their dates, and lets an admin choose
the active one of each type.

## Decisions

- **D1 — Paramètres gets sub-pages**, through the existing mechanism (`children` in `lib/access.ts`, `subRoutes()` in
  `router.ts`, `SubNav` drawn by `AppShell`), like Administration:
  - `general`, label "Général", path `""` (index): today's `ParametresPage.vue` content, moved as is;
  - `campagnes`, label "Campagne HelloAsso", path `campagnes`.
  - `ParametresPage.vue` becomes the thin layout (`AppShell` + `<RouterView>`). Both children: `access: "admin"`,
    `offline: "none"` (online only, nothing kept on the device). Server: `api/web/pages.py` must answer
    `/bureau/parametres/campagnes` with the entry page (check what it does for other sub-pages).
- **D2 — Storage: Firestore `app_settings` only.**
  - Membership: new key `HELLOASSO_MEMBERSHIP_CAMPAIGN`, value `Membership:<slug>`.
  - Competitions: existing key `HELLOASSO_ANNUAL_CAMPAIGN`, now saved as `Event:<slug>` (already parsed by
    `parse_campaign_identifier`; existing bare slugs / URLs keep working).
  - `/api/dashboard` (`get_target_slug`) reads `HELLOASSO_MEMBERSHIP_CAMPAIGN` first, then the `CAMPAIGN_SLUG` env
    variable, then the seasonal default slug. The last two are a temporary fallback, removed in a later change once
    production has a value chosen.
- **D3 — Which campaigns are listed.**
  - Membership table: `formTypes=Membership`; competitions table: `formTypes=Event`.
  - States `Public` and `Private` only (no `Draft`, `Disabled`, `Deleted`).
  - The active campaign is always listed, even when it no longer matches the filter (disabled, other type, not found):
    shown with a warning badge.
  - Sorted by `startDate`, newest first; `meta.createdAt` when `startDate` is missing (membership forms may have none).
  - To revisit if the club's competition form turns out to be a `PaymentForm`.
- **D4 — Columns** (from the list call only; no per-row `/public` call):

  | Column | Content |
  |---|---|
  | Campagne | `title` (+ `privateTitle` underneath when different), link to `url` in a new tab |
  | Slug | `formSlug`, small monospace |
  | État | Public / Privé badge |
  | Début / Fin | `startDate` / `endDate`, `dd/mm/yyyy`, "—" when missing |
  | Créée le | `meta.createdAt` |
  | Action | "Campagne active" badge, or "Choisir" button |

  Sale window (`saleStartDate` / `saleEndDate`) and tariffs: later, in a row details panel (one `/public` call on
  click), not in this plan.
- **D5 — Choosing a campaign.**
  - "Choisir" opens a confirmation dialog naming the current and the new campaign and the impact (membership: "the
    dashboard will show this campaign's registrations"; competitions: "new HelloAsso payments will only be matched
    against this form"). The change applies at once (the webhook and the dashboard read the setting on every call).
  - No automatic sync. After saving, a notice links to Compétitions › HelloAsso to run the sync.
  - No "clear" action: an empty setting breaks the sync and the webhook.
  - The HelloAsso items mirror is append-only (`sync_helloasso_mirror`): items of the former campaign keep their links.
- **D6 — Routes** (router `src/api/integrations/helloasso_campaigns.py`, Firestore-only: list it among the
  Firestore-only routers in `server.py`; add to `tests/test_route_inventory.py`; Pydantic `response_model` +
  `error_responses()`; regenerate `frontend/openapi.json` and `src/lib/api-schema.ts`):
  - `GET /api/helloasso/campaigns` — **coach** (default rule of `required_role`, no code): public HelloAsso data, so
    the Compétitions › HelloAsso pane may later show the active campaign to coaches. Answers
    `{membership: {active, campaigns[]}, competitions: {active, campaigns[]}, error}`; `active` = `{form_type, slug}`
    parsed from the setting, or null; `error` = null or the HelloAsso failure message (D7).
  - `PUT /api/helloasso/campaigns/{kind}` (`kind` = `membership` | `competitions`) — **admin**: new rule in
    `infrastructure/security/api_auth.required_role` (the default would let coaches write). Body `{form_type, slug}`.
    Shape check only: `form_type` must be the type of that kind (`Membership` / `Event`), slug non-empty. **No check
    that the campaign exists on HelloAsso** (it was listed by the app).
- **D7 — HelloAsso unreachable.**
  - A new listing function in `infrastructure/helloasso/api.py` passes `states` / `formTypes` and raises
    `HelloAssoApiError` on missing credentials or a request error, instead of returning `[]` / stopping silently.
    `get_campaigns()` and `fetch_all_pages()` keep their behaviour for the dashboard (out of scope).
  - The GET always answers **200** with `error: str | null` (like `POST /api/helloasso/sync`): it reads the two
    settings first (they don't need HelloAsso), then the lists. On a HelloAsso failure, `active` values are returned,
    `campaigns` are empty and `error` holds the French message (logged server side through `internal_error`).
  - The page then shows both active campaigns, an error banner and "Réessayer"; "Choisir" is unavailable until a list
    is loaded.
- **D8 — Dev**: the page works against the fake HelloAsso (`e2e/fakes/helloasso_fake.py`, enabled in dev by
  `HELLOASSO_API_BASE_URL` / `HELLOASSO_OAUTH_URL`). The fake filters `/forms` on `states` / `formTypes`; sample forms
  with dates are documented in `dev/README.md` (or loaded by a small dev script).

## Phases

Each phase ends with the checks green (`code_source/AGENTS.md` § Commands).

### Phase 1 — Membership setting in Firestore (backend only)

- `get_target_slug` reads `HELLOASSO_MEMBERSHIP_CAMPAIGN` → `CAMPAIGN_SLUG` → default (D2); a `Type:slug` value gives
  the slug (and the form type, so the dashboard no longer needs `get_campaigns()` to guess it — optional, keep the
  current lookup if simpler).
- Tests: the three fallback levels, `Type:slug` and URL values.

### Phase 2 — Listing route

- New listing function with filters and explicit errors (D7); fake HelloAsso filters on `states` / `formTypes`.
- `GET /api/helloasso/campaigns` (D3 sort and "active always listed", D6 answer); on HelloAsso error, 200 with the
  active values, empty lists and `error` set (D7).
- Tests: filtering, sort with missing `startDate`, active campaign outside the filter, HelloAsso error (active values
  still returned), route inventory, coach role.

### Phase 3 — Saving route

- `PUT /api/helloasso/campaigns/{kind}` + admin rule in `required_role` (D6); saves `Type:slug`.
- Tests: both kinds, wrong `form_type`, empty slug, unknown kind, coach refused (403), route inventory.
- Regenerate the OpenAPI files.

### Phase 4 — Paramètres sub-pages

- `children` for `parametres` in `lib/access.ts`, `subRoutes("parametres", …)` in `router.ts`, layout
  `ParametresPage.vue`, current content moved to `pages/parametres/ParametresGeneralPage.vue` (tests moved along).
- Server entry page for `/bureau/parametres/campagnes`.
- Tests: existing Paramètres tests pass on the Général sub-page; menu shows both children to admins.

### Phase 5 — Campagne HelloAsso page

- Service in `src/services/` on the typed client; page `pages/parametres/ParametresCampaignsPage.vue` with the two
  tables (D4), active badge / warning badge, confirmation dialog and post-save notice (D5), error banner + retry (D7).
- Vitest: rendering of both tables (dates, missing dates, states), choose → confirm → PUT → active badge moves,
  cancel, HelloAsso error state.

### Phase 6 — Wrap-up

- e2e (optional): choose a competition campaign against the fake, run the sync.
- Docs: `dev/README.md` (D8), `documentations/ARCHITECTURE.md` (setting keys), deployment guide note on
  `CAMPAIGN_SLUG` becoming a fallback.
- Bump `APP_VERSION` (`src/domain/constants.py`) and `code_source/VERSION` together.

## After the release

- Pick both campaigns in production, then remove the `CAMPAIGN_SLUG` fallback and the seasonal default slug.
- [#80](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/80): decide on `helloasso_ref`.
