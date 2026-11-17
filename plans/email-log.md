# Plan: e-mail log and last-contact dates on the competition page

> Source PRD: [#137](https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/137) (core of #134, prerequisite of #135, purge in #136).
> Branch: `feat/email_history_engine`.

## Architectural decisions

Durable decisions that apply across all phases:

- **Collection**: `email_log`, Firestore only (no `crm_` prefix, not in the SQLite cache, server-only access like
  `access_history`). One document per send action (one click on « Envoyer », one webhook notification, one cron
  e-mail), never one per recipient. Id: the date then a random part.
- **Entry**: `at` (ISO 8601 UTC), `author` (signed-in e-mail; `system` for the webhook and the cron; `serveur local` when the
  token check is off), `kind`, `template` (name or empty), `subject`, `competition_ids` (list), `member_ids` (list,
  top level for future `array-contains` lookups), `recipients` (list of `member_id` or null, `email` as sent, `name`,
  `status` `sent` / `failed`, `error`). **No body stored** (GDPR).
- **Kinds**: `competition_email`, `member_email`, `competition_all_paid`, `results_batch`, `attestation`,
  `access_invitation` (later `correction_request`, #135).
- **Lookup**: `array-contains` on `competition_ids`, no `orderBy`, sorted in Python → no composite index.
- **Contact summary** (pure domain): only `competition_email` counts toward the dates; every kind is listed. A
  recipient matches a competitor by member id, else by lower-cased e-mail when the competitor has no member id.
  A competitor's last contact: date of the last `sent`, `failed` when their latest attempt failed, else none.
- **Route**: `GET /api/competitions/{competition_id}/email-log` → entries (newest first) + summary
  (`last_competitor_email_at` and one item per competitor). Readonly and above (like the other competition reads),
  Firestore-only router, in the route inventory, OpenAPI + generated types regenerated.
- **Recording**: `record_send` writes once after the send loop and never raises: a store failure is a warning and
  a « not recorded » notice. `POST /api/send-email` answers it as an optional field.
- **Existing traces unchanged**: attestation sent date, invitation sent date, « all paid » setting.
- **Offline**: the page caches the last answer per competition; stale notice when shown offline; with no cache,
  « historique indisponible hors ligne », never « — ».

---

## Phase 1: Log competition e-mails; last-send date and history on the competition page

**User stories**: 1, 5, 6, 8, 10, 11, 12, 17, 18 (competition and member e-mails), 21, 22

### What to build

The shared e-mail dispatch records one `email_log` entry per send (`competition_email` with a competition,
`member_email` without), with the author passed by the route and each recipient's own status. The new read route
returns a competition's entries and its last `competition_email` date. The competition page fetches it when a
competition is opened and after a successful send; its header shows « Dernier envoi aux compétiteurs : … », which
opens a dialog listing the sends newest first (date, kind, author, template / subject, recipient count and failures),
each expandable to its recipients with address and status.

### Acceptance criteria

- [x] Firestore client: filtered query (`array-contains`)
- [x] E-mail log store (protocol, Firestore adapter, fake) with write and read tests
- [x] Contact summary (domain), competition-level date, parametrised tests
- [x] E-mail log service `record_send` and competition history
- [x] Dispatch records one entry per send, partial failure included (test)
- [x] Read route, role, inventory, Firestore-only list, OpenAPI + `api-schema.ts`
- [x] Competition page header date + history dialog, refetched after a send
- [x] Version bump

---

## Phase 2: Last contact on each competitor's row

**User stories**: 2, 3, 4, 7, 9, 24

### What to build

The summary adds one item per competitor (member id match, e-mail fallback). Each competitor row shows
« 📧 <date> », « échec » or « — »; clicking it opens the history dialog filtered to the sends that included that
competitor. A resend through the existing form updates the row.

### Acceptance criteria

- [x] Per-competitor summary: member id, e-mail fallback, failed then sent, sent then failed, siblings tracked apart
- [x] Row indicator and filtered dialog; frontend helpers tested with Vitest

---

## Phase 3: « Sent, but not recorded » notice

**User stories**: 16

### What to build

When the log store fails, the send still succeeds, a warning is logged and `POST /api/send-email` answers the
notice; the e-mail form shows « envoyé, mais non enregistré dans l'historique ».

### Acceptance criteria

- [x] Service test: a store failure leaves the send successful and returns the notice
- [x] Response field, OpenAPI regenerated, form message

---

## Phase 4: Offline history

**User stories**: 14, 15

### What to build

The page caches the last log answer per competition and shows it offline with the usual stale notice. With no cached
answer it says « historique indisponible hors ligne », in the header and on the rows, never « — ».

### Acceptance criteria

- [ ] Per-competition cache, stale notice
- [ ] « indisponible hors ligne » state (helper tested)

---

## Phase 5: Internal competition e-mails in the history

**User stories**: 13, 19, 20, 23 (« all paid »)

### What to build

The « all paid » summary (HelloAsso webhook) and the results batch (daily cron, several competitions) are recorded
with author `system`, kinds `competition_all_paid` and `results_batch`. They appear in the history labelled as
internal and never move the competitors' dates. The « all paid » setting still prevents sending twice.

### Acceptance criteria

- [ ] Both senders record their entry
- [ ] Summary test: internal kinds listed, ignored for dates; one batch entry covering several competitions

---

## Phase 6: Remaining senders

**User stories**: 18, 20, 23

### What to build

The attestation send moves from its router to a service and records an `attestation` entry with the member; access
invitations record an `access_invitation` entry. Existing traces (attestation sent date, invitation sent date) keep
working.

### Acceptance criteria

- [ ] Attestation send in a service, recorded
- [ ] Invitation e-mails (invite and resend) recorded
- [ ] Full checks pass (Python and frontend)
