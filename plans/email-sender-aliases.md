# Plan: Template sender address through Gmail "Send mail as" aliases

> Source issue: https://github.com/ALJ-Jonage-Escalade/ALJ-CRM/issues/65

## Why today's sender does not work

- **Lost before sending**: the competition and member e-mail screens post only subject and body (no `template_name`, no
  `sender_email`), so the server never sees the template's sender. Only the attestation and correction-request paths read it.
- **Rewritten by the transport**: the chosen address only goes into the `From` header (`infrastructure/mail/sender.py`).
  The Gmail API, called as the connected account (`admin@alj-escalade.fr`), replaces any `From` that is not one of that
  account's verified "Send mail as" aliases. Over SMTP the envelope stays the account, so DMARC fails or the server rewrites it.
- **Validation unrelated to reality**: `is_allowed_sender` accepts any `*@alj-escalade.fr`; the editor offers hard-coded
  `SENDER_SUGGESTIONS`. Mailpit shows the header as written, so the bug never shows in dev.

## Architectural decisions

Durable decisions that apply across all phases:

- **Allowed senders** = the connected account's own address + its verified aliases. Nothing else is ever sent as.
  - Gmail OAuth mode: `GET gmail/v1/users/me/settings/sendAs`; keep entries that are `isPrimary` or have
    `verificationStatus == "accepted"`. The current OAuth scope (`https://mail.google.com/`) already allows it: no new scope,
    no reconnect. A 403 gives the message "reconnectez le compte Google dans Paramètres".
  - SMTP mode (dev included): `SMTP_FROM_EMAIL` (else `SMTP_USER`) + the new variable `SMTP_SENDER_ALIASES`
    (comma-separated, read at call time through `SecretStore`, empty = none). `dev/dev.env` sets 2–3 `hogwarts.example` addresses.
  - Cached 5 minutes, no cache in dev (`runtime_env.is_dev()`), like `role_directory`.
- **Account address = the default sender**: `GMAIL_USER_EMAIL` in Gmail mode, `SMTP_FROM_EMAIL`/`SMTP_USER` in SMTP mode.
  `DEFAULT_SENDER_EMAIL` and `SENDER_SUGGESTIONS` are removed from `domain/club_emails.py`. An empty template sender means
  the account. System e-mails (invitations, all-paid notification, results cron) send as the account, so they are never refused.
- **Display name**: the template's `sender_name`, else `DEFAULT_SENDER_NAME` (unchanged text). Gmail's alias display name is ignored.
- **Refusal, never fallback**: a sender that is not the account and not in the alias list is refused (`domain.errors.Forbidden`
  → 403, message naming the address and what to do). When the list cannot be loaded (Gmail unreachable, scope refused), only
  the account address is allowed. Applies to every send path (dispatch, attestation, correction request).
- **Send request** (`POST /api/send-email`): carries `template_name` *or* `sender_email`, never both (400).
  - `template_name`: the sender (and name) come from the saved template; the subject and body sent by the page still win.
  - `sender_email`: free text only; any role with send rights may pick any allowed sender. The known-members recipient
    check for coaches is unchanged.
- **Template save** (`POST /api/email-templates`): `sender_email` must be empty or an allowed sender (400 otherwise).
  No migration of saved templates: a template whose sender is no longer allowed is flagged (see `GET`), and its sends are refused.
- **`GET /api/email-templates`** (coach): `sender_suggestions` → `sender_aliases` (account first, then aliases),
  `default_sender_email` = the account address, new `sender_aliases_error` (empty, or why the list is partial), and each
  template gets `sender_allowed: bool`.
- **Layers**: alias reading in `infrastructure/mail/` (one adapter per transport, no rule); the "allowed sender" rule and
  sender resolution in `services/communications/` (one function used by every send path); routers only parse and shape.
- **API contract**: regenerate `frontend/openapi.json` and `src/lib/api-schema.ts` in each phase that changes a schema.
- **Versioning**: bump `APP_VERSION` and `VERSION` together in each phase that ships.

## Out of scope (separate issues if wanted)

- Narrowing the OAuth scope (`https://mail.google.com/` → `gmail.send` + `gmail.settings.basic`).
- Recording the sender used in the e-mail history.

## Before shipping (club side)

In Gmail on `admin@alj-escalade.fr`, Settings › Accounts › "Send mail as": add `inscription@`, `contact@`,
`competitions@` (or whatever the club wants). Until then, templates using them are refused (by design).

---

## Phase 1: Server sends only as the account or a verified alias

### What to build

The alias adapters (Gmail `sendAs`, SMTP variable), the cached allowed-sender list, and one sender-resolution function in
`services/communications/` used by `dispatch_emails`, attestations, correction requests, invitations, the all-paid
notification and the results cron. `is_allowed_sender` and its domain rule are replaced by it; `DEFAULT_SENDER_EMAIL` and
`SENDER_SUGGESTIONS` are removed, the shipped default templates (`infrastructure/sqlite/connection.py`) get an empty sender.
`/api/send-email` rejects `template_name` + `sender_email` together. `SMTP_SENDER_ALIASES` added to `dev/dev.env`.
No UI change yet: the screens still send no sender, so they send as the account.

### Acceptance criteria

- [x] Gmail mode: the allowed list is the account + `accepted` aliases; a `pending` alias is not allowed (mocked `sendAs` response)
- [x] Gmail `sendAs` unreachable or 403: only the account is allowed, with a readable reason
- [x] SMTP mode: `SMTP_FROM_EMAIL` + `SMTP_SENDER_ALIASES`; empty variable → account only
- [x] A template whose sender is not allowed: the send is refused (403) on dispatch, attestation and correction-request paths
- [x] An empty sender sends as the account with `DEFAULT_SENDER_NAME`; invitations, all-paid and results cron use the account
- [x] `POST /api/send-email` with both `template_name` and `sender_email` → 400; with `template_name`, the template's sender is used
- [x] `grep DEFAULT_SENDER_EMAIL\|SENDER_SUGGESTIONS` finds nothing in `src/`
- [x] In the dev stack, an e-mail sent with an alias from `SMTP_SENDER_ALIASES` shows it as `From` in Mailpit; another address is refused

---

## Phase 2: Template editor offers only allowed senders

### What to build

`GET /api/email-templates` returns `sender_aliases`, the account as `default_sender_email`, `sender_aliases_error` and
`sender_allowed` per template; the save route refuses a sender outside the list (400). In `TemplateForm.vue` the sender
field becomes a select: "Par défaut (<account>)" (saved empty), then the aliases; a saved sender that is no longer allowed
stays shown and selected, with a warning. The template list shows "⚠️ expéditeur non autorisé" on those templates.
When the list is partial, the editor shows `sender_aliases_error`.

### Acceptance criteria

- [ ] `GET /api/email-templates` exposes `sender_aliases`, `sender_aliases_error`, `sender_allowed`; OpenAPI / TS schema regenerated
- [ ] Saving a template with a sender outside the list → 400 with the address in the message; empty sender accepted
- [ ] The editor offers only the default and the aliases; the placeholder / default label shows the real account address
- [ ] A template holding `inscription@` while it is not an alias shows the warning in the list and the editor
- [ ] Gmail unreachable: the editor shows the reason and offers only the default (and the current value, flagged)

---

## Phase 3: Send screens carry the sender

### What to build

Competition e-mail (`EmailForm.vue` / `email.ts` `sendBody`) and member e-mail (`MemberEmail.vue`): when a template is
picked, the request carries `template_name` and the form shows "De : <sender>" read-only (the template's, else the
account); a template not allowed shows the warning and disables sending. With free text, a "De" select of
`sender_aliases` (default: the account) and the request carries `sender_email`. The attestation screen shows the
template's sender read-only (it already sends `template_name`).

### Acceptance criteria

- [ ] With a template picked, the request has `template_name` and no `sender_email`; the e-mail leaves from the template's sender
- [ ] With free text, the request has `sender_email` from the select and no `template_name`
- [ ] A coach can pick any alias for free text; the recipient check still refuses unknown addresses
- [ ] A template whose sender is not allowed: warning shown, send button disabled
- [ ] Offline / template list unavailable: free text still sends as the account (offline path unchanged)
- [ ] Vitest: `sendBody` builds each of the two request shapes

---

## Phase 4: Documentation

### What to build

`documentations/guide_deploiement_cloud_run_helloasso.md`: drop the unused `GMAIL_SENDER_EMAIL` (the account comes from
the OAuth flow, `GMAIL_USER_EMAIL`), add a section "Adresses d'expédition" (create a "Send mail as" alias in Gmail, wait for
it to be verified, then pick it in Communications › Modèles; `SMTP_SENDER_ALIASES` in SMTP mode). `README.md` user section
on templates: what the sender list means and why a send is refused.

### Acceptance criteria

- [ ] No reference to `GMAIL_SENDER_EMAIL` left in the docs
- [ ] The guide explains how to add an alias and how it shows up in the CRM
- [ ] `dev/README.md` mentions `SMTP_SENDER_ALIASES` for testing senders in Mailpit
