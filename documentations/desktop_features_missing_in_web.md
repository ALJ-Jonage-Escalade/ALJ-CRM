# Desktop features not available in the web app

> Written 2026-10-20 when the PySide6 desktop app was removed (branch `feat/remove_windows_app`, base `main` @ `e7e0624`).
> Method: each desktop page (`src/presentation/pages/*.py`, last version in git history) was compared with
> `web/bureau/*.html`, `web/index.html` and the API routes in `src/server.py` / `src/api/`.
> To read the removed code: `git show e7e0624:code_source/src/presentation/pages/<page>.py`.

## Missing on the web

| Desktop feature | Desktop page | Removed code | Backend logic kept? | Notes |
|---|---|---|---|---|
| Bulk e-mail to filtered members (season, slot, status, "registered after"), choice of recipient address (member / 2nd e-mail / HelloAsso payer), attestation PDF and WhatsApp invitation/QR as attachments, duplicate removal | Communications | `pages/communications.py` | Partly: `/api/send-email`, `/api/preview-email`, `infrastructure/mail/*` | The web sends to one member at a time (`adherents.html`) or to a competition campaign (`competitions.html`). `communications.html` only manages templates. |
| A4 emergency-contacts book (Excel, club style) | Exports | `exports/emergency_contacts.py` | No | Contacts can only be viewed per member in the mobile directory (`web/index.html`). |
| Excel export of former members not re-registered | Exports | worker in `presentation/workers.py` | Yes: "Non réinscrits" filter in `SqliteRepository` (`infrastructure/sqlite/repository.py`) | Needs a route + button. |
| MyCompet rankings export (Excel) | Exports | worker | Yes: `infrastructure/mycompet/scraper.scrape_mycompet` (no caller anymore) | Per-competition results exist on the web ("Trouver les résultats"). |
| Import of the autonomy list `Autonomes_*.xlsx` (red badges) | FFME | `pages/ffme.py` | Yes: `SqliteRepository.merge_autonomes_data` (no caller anymore) | Badges can only be edited member by member. |
| Import of the previous season's FFME file | FFME | `pages/ffme.py` | Yes: `SqliteRepository.import_old_season_ffme` (no caller anymore) | |
| Google Contacts sync (labels per group, address choice) | Gmail contacts | `infrastructure/google/contacts.py`, `infrastructure/google/gmail_auth.py`, `pages/gmail_contact.py` | No | Would need the Contacts scope on the web OAuth client. |
| WhatsApp QR code per slot | Groups | `pages/groups.py` | Partly: `infrastructure/qrcodes/` | The WhatsApp invitation text exists (`/api/whatsapp-template`), but there is no QR generation in the UI. |
| Address quality: list of unrecognised addresses, suggested correction, manual geocoding | Reports | `pages/reports.py` | Partly: `server.geocode_missing_addresses` (background) | The web has the map (`/map`), but no correction screen. |
| Dashboard (statistics, recent activity) | Dashboard | `pages/dashboard.py`, `components/qt_charts.py` | Yes: `GET /api/dashboard` (no web caller) | `/bureau/` is a link portal; the pivot table (`/pivot`) covers part of the statistics. |
| Word (.docx) attestations, batch generation into a folder | Documents | `exports/attestation_word.py`, `doc/template/ATTESTATION DE PAIEMENT_adulte.docx` | No | The web generates and sends PDF attestations one member at a time (`/api/attestations/preview`, `/send`); no batch download. |
| Built-in help centre (input files, sync cycle) | Help | `pages/help.py` | No | |

## Partly covered

| Desktop feature | Web equivalent | Gap |
|---|---|---|
| "Cours" attendance sheet from `doc/template/Cours - Template-Vide.xlsx` (`exports/presence_cours.py`) | `POST /api/presence/export` (`exports/presence_sheets.py`, variants `cours` / `autonome`) | Different layout; the `Cours.xlsx` template is gone. |

## Covered (no action)

| Desktop feature | Web equivalent |
|---|---|
| Members list, details, add, edit, change group | `bureau/adherents.html` |
| FFME import with manual matching of licensees not found | `bureau/outils.html` → `/api/ffme/preview`, `/api/ffme/import` (`manual_matches`) |
| FFME CSV export + pre-export summary | `/api/ffme/export`, `/api/ffme/stats` |
| Slots: instructors, HelloAsso tariffs, birth-year limits, weekly view, planning export | `bureau/planning.html` |
| Competitions, coaches, HelloAsso payment matching, reminders, CSV exports | `bureau/competitions.html`, `/api/competitions/*` |
| E-mail templates, WhatsApp invitation text | `bureau/communications.html` |
| Map, pivot table | `bureau/outils.html` (`/map`, `/pivot`) |
| Google OAuth connection / token test | `bureau/parametres.html` (`/api/auth/google/*`) |
| HelloAsso sync | `/api/helloasso/sync` |
| Daily MyCompet results task (Windows task at 07:00) | Cloud Scheduler job `batch-resultats-competitions`, working once `fix/job_comp_update` is merged (see `plan_fix_job_comp_update.md` on that branch) |

## No longer needed

| Desktop feature | Why |
|---|---|
| Local DB ↔ Firestore push/pull, Drive upload, local file diagnostics (`infrastructure/firestore/sync.py`, Settings / Reports pages) | Firestore is the source of truth; the server rebuilds its SQLite cache (`/api/cloud-db/status`, `/api/cloud-db/sync`). |
| Log viewer, local server restart | Cloud Run logs (Cloud Logging). |
| Portable package, launcher, auto-update, installer | No desktop client anymore. |
