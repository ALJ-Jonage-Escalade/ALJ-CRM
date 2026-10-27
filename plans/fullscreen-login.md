# Full-screen login gate

## Problem
There is no login page: `AppShell.vue` shows the `#gate` inside every page. Signed out, the menu still lists the
8 office pages (`nav` falls back to `PAGES` while the role is unknown), with the header and the account chip; every
link only leads to the same gate. The Google sign-in error (`SIGN_IN_ERROR_KEY`) is rendered inside the
Compétitions page slot, which is not rendered while signed out: a failed sign-in shows no explanation.

## Decisions
| Verdict (`lib/access.ts`)          | Display                                                                   |
|------------------------------------|---------------------------------------------------------------------------|
| `signIn`                           | full screen: logo, sign-in card (+ sign-in error), version                |
| `pending`                          | full screen splash: logo, "Vérification de la connexion…"                 |
| `unverified`, online               | full screen: error, Réessayer, Se déconnecter                             |
| `unverified`, offline              | normal shell and full menu; the gate links to Annuaire and Compétitions   |
| `noAccess`                         | full screen: "Connecté en tant que <email>", links to the pages the role may open (Compétitions for read-only), Se déconnecter |
| `adminOnly`, `allow`, `offline`    | unchanged                                                                 |

- Offline mode must never break: a signed-in user offline keeps the menu to reach the pages readable offline.
- Implemented in `AppShell` (no `/login` route): the address stays the requested page, so the return after sign-in,
  the server's `_SPA_PAGES` and the service worker are unchanged.
- The `#gate*` ids are kept (e2e); `#who` only exists in the shell.
- Full-screen background `bg-side` (the menu's), white card `max-w-sm`, `AppBrand` (name, version) above; bottom padding keeps the
  dev banner clear.
- Logout from the full-screen card goes through the shell's `logout()` (asks before losing offline changes).

## Changes
1. `components/AppShell.vue`: `fullscreen` computed; no aside/header/`#who` in that mode; sign-in error, account
   e-mail, logout and offline links in the gate.
2. `pages/CompetitionsPage.vue`: remove the sign-in error block (now in the shell).
3. Tests: `AppShell.test.ts`; e2e `test_service_worker.py` (no menu signed out offline), `test_auth.py::test_logout`,
   `bureau/test_accueil.py::test_non_staff_sees_no_office_menu` (pages listed in the gate).
4. Version bump (`APP_VERSION`, `VERSION`).
