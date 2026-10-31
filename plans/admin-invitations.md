# Plan: admin invitations replace access requests

> Branch: `feat/account_access_email`. Follows [admin-access.md](admin-access.md) (Administration › Accès).

## Why

Any Google account that signed in left an access request for the admins to answer. Access is now by invitation only:
an admin invites an address with a role, the app e-mails a link, and the person gets the role on their first sign-in
within 7 days.

## Decisions

- **No token.** Google stays the proof of identity: the role is keyed by the verified e-mail, as before. The e-mail
  is a convenience; a forwarded link gives nothing to another account.
- **An invitation is an `access_roles` entry** with four more fields: `invited_at`, `invitation_expires_at`
  (+7 days), `invitation_sent_at` (null: the e-mail failed) and `accepted_at`.
  - `RoleDirectory.role_of`: an entry whose `invitation_expires_at` is set and past gives no role (the bootstrap
    address keeps its emergency admin role). Entries without the field (older ones, bootstrap) never expire.
  - Acceptance: `/api/me`, for an entry that still has `invitation_expires_at`, clears it and sets `accepted_at`.
    Not limited to once a day: a failed write is retried on the next page load.
- **Access requests removed entirely**: store, rules, routes, page section, history actions. `/api/me` writes nothing
  for an unknown address. The leftover `access_requests` documents are deleted once by hand (no request was ever made).
- **Routes** (`api/admin/access.py`, admin only):
  - `POST /api/admin/access/roles` invites (body unchanged) and answers `AccessInvitation` (`entry`, `email_sent`,
    `email_error`). An address already listed: 409 `already_listed`, or `already_invited` when it is an invitation.
  - `POST /api/admin/access/roles/{email}/invitation` resends: new 7 days, new e-mail, history `invitation_resent`.
    409 `not_invited` for an accepted or older entry.
  - PATCH (role, name) and DELETE unchanged, also on a pending invitation. A role change does not resend.
- **History actions**: `added` kept for older entries, `invited` and `invitation_resent` added.
- **E-mail**: fixed template in code (`services/access/invitations.py`), default club sender, plain text + HTML.
  A send failure keeps the invitation; the page shows the reason and « E-mail non envoyé » until a resend works.
- **Link**: `APP_PUBLIC_URL` (Cloud Run variable, guide § 4) + `/bureau/`; unset: the `Origin` of the admin's page (Cloud Run's
  `request.base_url` says `http://`: uvicorn runs without trusted proxy headers).
- **`/api/me`** adds `invitation_expired_at` (set only without a role and with an expired invitation). The gate shows
  the signed-in address and says either « no invitation for this address » or « invitation expired on … ».
- **Google only**: the e-mail and the form say to sign in with a Google account using that exact address, and how to
  create one without Gmail. Gmail dot/alias variants are not normalised.

## Checklist

- [x] Store: invitation fields, requests removed (`access_store.py`, `tests/support/fake_access.py`)
- [x] Directory: expired invitation gives no role, `expired_invitation_of(email)`
- [x] Rules: `invite`, `renew_invitation`, `mark_invitation_sent`, `accept_invitation`; requests removed
- [x] Invitation e-mail + link (`services/access/invitations.py`)
- [x] Routes, schemas, `/api/me`, route inventory, OpenAPI + `api-schema.ts`
- [x] Accès page: invite form, status column, Renvoyer, requests section removed
- [x] Gate (`AppShell.vue`) and `composables/auth.ts`
- [x] Seed, e2e, unit tests; deployment guide (`APP_PUBLIC_URL`); version bump
