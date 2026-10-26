# ALJ-CRM — Fix the daily MyCompet results job (branch `fix/job_comp_update`)

> Written 2026-10-20 against `main` @ `847e666`, re-checked 2026-10-26 against `096ca63` (after the `server.py` split,
> the Windows app removal, the SQLite file split and the Vue migration). The production checks below are **read-only**
> (`gcloud scheduler jobs describe/list`, `gcloud logging read`, done 2026-10-20). Nothing was triggered.

## 1. Context

Every morning, the club wants the results of past competitions fetched from MyCompet (FFME) and written to the
competition documents, with a summary e-mail.

- **Cloud Run.** `POST /api/competitions/cron/fetch-results` (`src/api/competitions/results.py:28`) runs
  `CompetitionResultsBatchService.run_daily_batch()`. It is called by a Cloud Scheduler job, and by hand from the
  "Paramètres" page (`frontend/src/pages/ParametresPage.vue:167` → `competitionsApi.fetchAllResults`,
  `frontend/src/services/competitions.ts:44`, always with `?force=true`).
- **Windows (gone).** The desktop app and its scheduled task scripts (`scripts/run_batch_resultats.bat`,
  `installer/creer_tache_resultats_07h.ps1`) were removed in `eec18c1` (#17). Only the task already registered on the
  club PC (`ALJ_Escalade_Batch_Resultats_07h`) may still exist (see § 5).

The Cloud Scheduler job was created by hand. `documentations/ARCHITECTURE.md` (lines 43, 135, 271) names it and its
target, but its configuration (deadline, auth, retries) and the command to recreate it are **not in the repo**.

## 2. Findings (production, read-only, 2026-10-20)

### 2.1 The Scheduler job

| Field | Value |
|---|---|
| Name | `batch-resultats-competitions` (europe-west1, project `smart-amplifier-510811-n6`) |
| Schedule | `0 7 * * *`, `Europe/Paris`, ENABLED |
| Target | `POST https://alj-escalade-api-bdxfydatoa-ew.a.run.app/api/competitions/cron/fetch-results` |
| Attempt deadline | **180 s** |
| Auth | **none** (no OIDC token) |
| Retries | none (`maxRetryDuration: 0s`, no retry count) |
| Last update | 2026-10-14T06:38Z |

Request logs: every run since 2026-10-14 returned **HTTP 200**, with latency between 9.6 s and 34 s.

### 2.2 The batch does nothing (root cause)

Application log of the 2026-10-20 run (code of that time):

```
🚀 [BATCH_RESULTATS] Démarrage du batch quotidien (2026-10-20T05:00:39) — Notif: <club address>
⚠️ [BATCH_RESULTATS] Lecture Firestore impossible, repli SQLite : type object 'FirestoreClient' has no attribute 'get_collection'
🔍 [BATCH_RESULTATS] 0 compétition(s) éligible(s) sans résultats détectée(s).
ℹ️ [BATCH_RESULTATS] Aucun nouveau résultat à notifier aujourd'hui.
```

- `src/services/competitions/results_batch.py:115` calls `FirestoreClient.get_collection("competitions")`.
  That method **has never existed** (`git log -S get_collection -- src/infrastructure/firestore/client.py` finds nothing).
  The listing method is `FirestoreClient.list_documents` (`src/infrastructure/firestore/client.py:186`).
- The SQLite fallback has since been removed, but the outcome is the same: the `AttributeError` is caught by a broad
  `except Exception` (`results_batch.py:120`), printed as a warning ("Lecture Firestore impossible : …"), and
  `list_pending_competitions` returns an empty list. The batch finds **0 pending competitions**, sends nothing, and
  returns 200. Scheduler reports success every day.

**Result: daily results have never been fetched automatically.**
Only the manual "Trouver les résultats" action per competition works (`POST /api/competitions/{id}/fetch-results`,
`results.py:47`, which uses `FirestoreClient.get_document`).

### 2.3 Problems that appear once 2.2 is fixed

1. **Timeouts.** Scheduler gives up after 180 s and Cloud Run after 300 s (`code_source/scripts/deploy_cloud_run.sh:207`).
   The batch is sequential over *every* past competition without results. That list keeps growing, because
   competitions with no ALJ results are retried forever. For each competition without a URL, `find_mycompet_result_url`
   (`src/infrastructure/mycompet/scraper.py:273`) fetches the FFME archives (10 s timeout), then probes up to 70
   pages × 3 s (`scraper.py:322`), so up to about 220 s **for one competition**. The first fixed run will very likely
   time out. Scheduler marks it failed, but the request keeps running on Cloud Run (in a thread pool,
   `results.py:41`) until the 300 s limit, possibly in the middle of writes.
2. **Hard-coded probe range** `range(13710, 13640, -1)` (`scraper.py:322`): newer result IDs can never be found by
   probing, so it only costs time.
3. **Public endpoint (audit A29, `documentations/plan_api_only_front.md:661`).** The path is in `PUBLIC_PATHS`
   (`src/infrastructure/security/api_auth.py:86`). Anyone can start the scraping batch, and `?email=` sends the
   summary to any address. With the job relying on it, this has to be closed.
4. **Document key.** The batch takes `cid = comp.get("id") or comp.get("doc_id")` (`results_batch.py:131` and `:436`)
   and writes with `FirestoreClient.update_fields("competitions", cid, …)`. Raw `list_documents` returns the Firestore
   key as `_doc_id` (not `doc_id`), and legacy competitions may live under a random key different from `str(id)`.
   `_list_comp_docs()` (`src/infrastructure/firestore/competitions/base.py:80`, inherited by
   `CompetitionFirestoreRepository`, `src/infrastructure/firestore/competition_repository.py:46`) already deduplicates
   and moves them to the canonical key `str(id)` (it writes and deletes documents to do so), so use it rather than
   the raw listing.
5. **Lost updates.** The batch rewrites the whole `participants` array (`results_batch.py:218`), read at the start of
   the run. A participant edited on the web during the run (can take minutes) is overwritten. Re-read the document just
   before writing, or only patch the ranking fields of the matched participants.
6. **Cache (minor).** The batch writes Firestore directly. The route calls `invalidate_cache()`
   (`services/competitions/store.py:44`) at the end (`results.py:44`), which only clears the instance that served the
   request (max-instances 2). The other instance's cache expires after `ALJ_COMPETITIONS_CACHE_SECONDS` (default 5 s,
   `store.py:31`), so results are stale there for a few seconds at most. No change needed.
7. **Scraping from GCP IPs.** MyCompet/FFME may block or throttle datacenter IPs. This has never been tested on a schedule.
8. **Notification address.** It is now read from the Firestore `app_settings` collection through
   `AppSettingsRepository.get` (`results_batch.py:45`), no longer from the SQLite mirror. The 2026-10-20 log shows it
   resolves. Check `GET /api/settings/competitions-results` on Cloud Run after the deploy.
   Side note: the batch no longer touches SQLite at all, yet `results.py`'s module docstring, `server.py:36-38/105-107`
   and `tests/test_api_foundations.py:121` (`test_results_cron_runs_on_refreshed_cache`) still say it reads and writes
   the SQLite cache. Check whether any route of `results.py` still uses it; if not, update those comments (moving the
   router to the Firestore-only list is optional and out of scope).

## 3. Fix plan

### a. Read the competitions correctly
- In `CompetitionResultsBatchService.list_pending_competitions`, replace `FirestoreClient.get_collection("competitions")` with
  `CompetitionFirestoreRepository._list_comp_docs()` (or add a public wrapper; it is private today), and use its
  canonical key (`str(id)`) for writes.
- Stop swallowing the error: catch `FirestoreError` only, log at error level (`logger.error`, not `print`), and let the
  endpoint return a non-2xx status (e.g. 503 through `api.responses.error()` + `error_responses()`), so Scheduler shows
  the failure. (The SQLite fallback itself is already gone.)
- Unit tests with the fake Firestore (`tests/support/fake_firestore.py`, `use_fake_firestore`, already imported by
  `tests/services/competitions/test_results_batch.py`): past competition without results → listed; with
  `resultats_synced_at` + rankings → not listed; future → not listed; legacy random key → written under `str(id)`;
  Firestore error → the endpoint returns an error, not 200 with 0 competitions.

### b. Bound the run (must ship with **a**, otherwise the first run times out)
- Only competitions that ended in the last N days, unless `force=true` (admin only). N is the `app_settings` key
  `RESULTATS_BATCH_WINDOW_DAYS` (default 30, read through `AppSettingsRepository`, invalid value → default + warning),
  so the club can change it without a deploy. `run_daily_batch` / `list_pending_competitions` also take
  `window_days: int | None = None` and `today: datetime.date | None = None` (`None` = setting / real date), so tests
  set both directly (see f).
- Overall time budget (e.g. 150 s, under the 180 s deadline): stop cleanly between competitions, report
  `"partial": true` and how many are left, so the next run continues. Pass the budget and the clock as parameters
  (`time_budget_s`, `clock=time.monotonic`) so a test can simulate an overrun without sleeping. Add these fields to `BatchReport`
  (`api/competitions/schemas/results.py`), then regenerate `frontend/openapi.json` and `src/lib/api-schema.ts`.
- Remove the hard-coded probe, or limit it to a few IDs above the highest known `url_resultats`.
- Optional: remember failed attempts (`resultats_last_try_at`) and try each competition at most once a day.
- Fetch the FFME archives page once per run, not once per competition.

### b2. Do not trust an auto-detected URL without a date check
- `find_mycompet_result_url` matches loosely: venue only (`clean_lieu in clean_full`), or one shared word for a
  two-word name. Run unattended, a wrong page (same venue, earlier season) often matches several ALJ licences.
  The batch then writes wrong rankings, saves `url_resultats` + `resultats_synced_at` (`has_results()` becomes
  true, so it is never retried) and e-mails them.
- In the batch, accept an **auto-detected** URL only if the competition date shown on the MyCompet page (or on the
  FFME archive entry) matches `date_competition` .. `date_fin` (± 1 day). Otherwise write nothing and list the
  competition in the e-mail as "URL à saisir manuellement". A URL entered by hand (`url_resultats` already set)
  is still trusted.
- `comp_date` is already passed to `find_mycompet_result_url` but not used today. No date parsing exists in
  `scraper.py` yet: capture the date format from a real page and test it with a **synthetic** HTML fixture
  (no real athlete names in `tests/`).

### c. Write safely
- Re-read the competition just before writing and patch only the ranking fields of the matched participants
  (`classement`, `total_categorie`, `resultat_ffme`, `categorie_ffme`, `performance_ffme`, `resultat_synced_at`),
  plus `url_resultats` / `resultats_synced_at` on the competition. (There is no SQLite write branch any more.)

### d. Secure the endpoint (audit A29)
- Job side: `gcloud scheduler jobs update http batch-resultats-competitions --location europe-west1
  --oidc-service-account-email <scheduler-sa> --oidc-token-audience https://alj-escalade-api-bdxfydatoa-ew.a.run.app`
  (create a dedicated service account with no other roles).
- App side: remove the path from `PUBLIC_PATHS`. Without an explicit rule, `required_role` would fall back to `COACH`
  (`api_auth.py:163`): add an `ADMIN` rule for this path, plus a bypass for a Google OIDC token whose `email` is the
  scheduler service account and whose `aud` is the service URL (verify with the Google JWKs; `PyJWT[crypto]` is
  already a dependency). The Vue button sends the admin session, so it keeps working.
- Ignore `?email=` unless the caller is an admin. `force=true` is admin only.
- Update the tests that call the cron route without auth: `tests/web/test_bureau_web.py:77`,
  `tests/test_api_foundations.py:126`, and the public-route list in the `tests/test_route_inventory.py` docstring (line 4).
- **Order:** update the job first (adds the token, harmless for the public endpoint), then deploy the app change.
  Otherwise the next 07:00 run gets 401.

### e. Document the job
- Add a "Cloud Scheduler" section to `documentations/guide_deploiement_cloud_run_helloasso.md` (nothing there yet):
  name, schedule, time zone, target, deadline, OIDC service account, and the full `gcloud scheduler jobs create http …`
  command to recreate it.
- `documentations/ARCHITECTURE.md:271` already mentions the job but says "créée à la main dans GCP (hors dépôt)":
  point it to the new guide section and mention the OIDC auth (also line 135, the list of URLs called from outside).
  Add a deployment note in `README.md` (no mention yet).

### f. Tests with a fake MyCompet
Today nothing tests the batch end to end: `test_results_batch.py` patches `list_pending_competitions`, and
`find_mycompet_result_url` / `fetch_and_parse_mycompet_results` call the real sites (FFME archives, MyCompet).

**1. Configurable URLs (dev only).** In `infrastructure/runtime_env.py`, next to `helloasso_api_url()`, add
`mycompet_base_url()` (`MYCOMPET_BASE_URL`, default `https://mycompet.ffme.fr`) and `ffme_archives_url()`
(`FFME_ARCHIVES_URL`), both through `_dev_override` (ignored outside dev mode, like HelloAsso). `scraper.py` builds
its URLs from them (`normalize_result_url`, the archive fetch, the probe). Allow only local addresses for the two
variables in `dev/check_env.py`, as for HelloAsso.

**2. A fake page built from a real one.** Save one real MyCompet results page and the FFME archives page by hand,
**outside the repo** (`scripts_temporaires/`, git-ignored: they hold real names, licences and minors). A committed
script `dev/make_mycompet_fixture.py <saved.html>` turns the results page into a template:
- keeps the structure the parser relies on (`regroupement` / `regroupement-header` divs, rows with
  `palmares_<licence>` links and `<strong>` names, the `cr-Titre` title, the date block used by b2);
- fakes **all** the data, not only the club rows: a real page lists every climber of each category (full name,
  club, licence number inside the `palmares_<licence>` link), many of them minors. Every row gets an invented name,
  an invented club and a licence in a reserved range no real licence uses (e.g. `99xxxxx`). Names are **not** made
  with Faker (realistic names can match real people): they combine two fixed lists of clearly invented first names
  and surnames kept in the script (e.g. `Zorbalt`, `Quillmere`), checked to give no hit in the FFME search before
  committing. Anything else that identifies a person goes too: birth year, age, club code, judges, organiser
  contacts, photos;
- drops scripts, tracking, analytics and external links, and the real competition number from the URLs;
- replaces the title, the venue and the date with placeholders (`{{TITLE}}`, `{{VENUE}}`, `{{DATE}}`), and leaves a few
  empty slots per category for club athletes (`{{CLUB_ROWS}}`).

The template goes to `tests/support/mycompet/results_template.html`, **not `tests/fixtures/`** (git-ignored for
personal data: the file would silently stay out of git). A test checks it contains no licence outside the
reserved range, no name or club outside the script's invented lists, and no `mycompet.ffme.fr` / `ffme.fr` link.
Review the generated file by eye before the first commit. The same is done for a small archives page (`archives_template.html`) listing the target competition **and a
decoy** (same venue, an earlier season) to test b2.

`tests/support/mycompet/render.py` fills the template:
`render_results(title, venue, date, club_athletes=[{nom, prenom, licence, categorie, classement}], club="AL JONAGE")`.
Club athletes are injected at render time instead of being hard-coded: seed members come from Faker, so their names
would drift with a Faker update.

**3. Unit tests (no network).** A `requests.get` stub (`unittest.mock.patch`, no new dependency) routing by URL to
`render_results` / the archives page, and failing the test on any other URL, with the fake Firestore:
- end to end: a past competition (`today` injected) with participants → the batch finds the URL through the archives,
  writes only the ranking fields under `str(id)`, sends the e-mail (`EmailRepository.send_email` patched) with the
  expected rows;
- window: with `window_days=30`, a competition ended 35 days ago is skipped, one ended 5 days ago is processed;
  `window_days=60` or `force=True` includes both; the setting is honoured when the parameter is `None`;
- b2: the decoy (wrong date) is rejected, nothing is written, the e-mail lists "URL à saisir manuellement"; a hand-set
  `url_resultats` is trusted;
- c: a participant edited between the read and the write (fake Firestore changed from the stub) keeps its edit;
- b: a clock that jumps past the budget after the first competition → `partial: true`, the rest left for the next run;
  the archives page is fetched once per run;
- errors: MyCompet 500 / timeout for one competition → the others are still processed; Firestore error → non-2xx;
- `parse_mycompet_results_html` and the new date parser on the template (names, licence, rank, total per category).

**4. Fake server for dev and e2e.** `e2e/fakes/mycompet_fake.py` (port 8096, same pattern as `helloasso_fake.py`)
serves `/resultat/resultat_<n>` and the archives page from the templates, with `PUT /_e2e/state` to load the
competitions to serve (title, venue, date, club athletes). An e2e test (`e2e/test_competition_results.py`):
admin clicks the batch button on the Paramètres page (`data-testid="results-run"`) → rankings shown on the competition page, e-mail
in the fake SMTP. For the dev stack, `dev/README.md` explains how to start it and set `MYCOMPET_BASE_URL` /
`FFME_ARCHIVES_URL`.

**5. Seed.** Add a competition that ended 5 days ago, with participants, next to the existing one 35 days ago
(`dev/seed/seed_emulator.py:304`), so the window is visible in dev. A small `dev/seed/mycompet_state.py` pushes the
matching state to the fake server from the seeded participants.

## 4. Verification
- `uv run ruff check src tests && uv run mypy && uv run pytest tests` (new tests from a/b/c/d), plus
  `uv run python dev/export_openapi.py --check` and the frontend checks if `BatchReport` changed.
- Dev stack (emulator) with the fake MyCompet (f.4) and the new seed (f.5): the Paramètres batch button
  (admin) processes the competition ended 5 days ago, skips the 35-day one unless forced, writes the rankings and sends
  the summary to Mailpit. The e2e test covers the same path in CI.
- Deploy to the test revision (`./scripts/deploy_cloud_run.sh --test`). **It uses production data: the summary e-mail is real
  and results are written.** Only call the test URL by hand with the team's OK.
- After the production deploy, the next morning:
  `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="alj-escalade-api" AND textPayload:"BATCH_RESULTATS"' --freshness=1d`
  should show `N compétition(s) éligible(s)` with N > 0, no `get_collection` error, and an end before the deadline.
  (If the batch logs move from `print` to the `alj` logger, check the filter still matches: use `jsonPayload` /
  `textPayload` as the log format requires.)
  `gcloud scheduler jobs describe batch-resultats-competitions --location europe-west1` should show `status` empty (success).
- Unauthenticated call: `curl -X POST <URL>/api/competitions/cron/fetch-results` must return 401.
- Manual trigger (`gcloud scheduler jobs run batch-resultats-competitions --location europe-west1`) runs on production
  data and sends a real e-mail: only with the team's OK.

## 5. After the fix
- On the club PC, if the old task is still registered: `schtasks /Delete /TN ALJ_Escalade_Batch_Resultats_07h /F`.
  Its scripts were deleted with the desktop app (`eec18c1`), so it can only fail now.
- Mark A29 as fixed in `documentations/plan_api_only_front.md:661`.
