# Plan: sub-menus instead of in-page tabs

> Branch: `feat/rethink_menu`. Design settled by a grilling session (2026-10-27).

The pages that grew tabs (Compétitions: 4 sections, Outils: 6 tabs) get crowded: each tab keeps gaining features.
Their tabs become sub-pages listed in the menu, through one reusable mechanism that any page can adopt.

## Decisions

- **D1 — Menu-wide pattern.** A `PAGES` entry (`lib/access.ts`) gets optional `children`; the role filter, the current
  page highlight and the router guards treat a child like a page. One component, `SubNav.vue`, draws them. Pages
  without children are unchanged.
- **D2 — Real nested routes.** `/bureau/competitions/helloasso`, `/bureau/outils/ffme`… Each child is a route with its
  own `meta.access`. The parent route component is a thin layout (`AppShell` + `<RouterView>`).
  - Server: `api/web/pages.py` answers `/bureau/<page>/<sub>` and `/competitions/<sub>` with the entry page.
  - Service worker: the `APP_PAGES` allowlist (`sw.ts`) already matches sub-paths; no change.
  - Former links redirect: `?section=<x>` → `<page>/<x>`, `?tab=<x>` → `<page>/<x>` (bookmarks, Adhérents' FFME
    links, which are updated too).
  - The `/competitions` PWA alias gets the same children.
- **D3 — Phones: a chips strip under the header.** The bottom bar is unchanged. Tapping a parent opens its index
  child; the shell draws the visible siblings as a horizontally scrollable strip under the title.
  **Desktop: accordion in the sidebar.** Clicking a parent navigates to its index child; only the active parent is
  expanded (children indented, current one `aria-current="page"`, parent in a lighter "section active" style). No
  toggle without navigating. A role that sees a single child gets the entry as today: no strip, nothing expanded.
- **D4 — First child = index route** (empty path). `/bureau/competitions?id=12`, `/competitions` (PWA start, Google
  sign-in callback) keep working as is. Label of the Compétitions index child: "Compétitions" (to be renamed later).
- **D5 — Shared state in the parent layout.** The layout owns what the children share (Compétitions: competitions,
  contacts, members, coaches resources, outbox and replay, network state, `syncInfo`) and passes it through one
  `provide`/`inject` key (`COMPETITIONS_KEY`, like `WRITER_KEY`). A child loads only its own data (HelloAsso items).
  Keeping children mounted is opt-in per parent: `meta.keepAlive` wraps the `RouterView` in `<KeepAlive>` (Outils on,
  Compétitions off).
- **D6 — Offline per child**, `offline: "read" | "staffCopy" | "none"`:
  - `read`: shown offline (as `offlineRead` today);
  - `staffCopy`: shown offline only if the parent layout says the device holds a staff copy (Compétitions: the
    competitors' contacts are kept, today's `canWrite`). The rule stays in the layout, not in `access.ts`;
  - `none`: online only. Offline it stays in the menu, disabled, with "📴 En ligne uniquement"; opened directly, it
    redirects as D8.
  - Compétitions layout, list, Bilan and Coachs stay in the main bundle (offline without the service worker cache);
    HelloAsso may be lazy.
- **D7 — Titles.** `<h1>` = the child's label (the parent's for the index child); no breadcrumb, the expanded menu gives
  the context. Browser title: "Bilan · Compétitions".
- **D8 — Refused child → parent index.** A child the role may not open (e.g. a coach on `/bureau/outils/ffme-import`),
  or a `none` child offline, redirects to the parent's index child with a toast ("⛔ Import FFME : réservé aux
  administrateurs"), through the `?reserve=` mechanism. One code path. The parent's own access still applies first
  (Accueil, as today).

## Children

| Parent | Child (path) | access | offline |
|---|---|---|---|
| Compétitions | Compétitions (index) | viewer | read |
| | HelloAsso (`helloasso`) | staff | none |
| | Bilan (`bilan`) | staff | staffCopy |
| | Coachs (`coachs`) | staff | staffCopy |
| Outils | Carte (index) | staff | none |
| | TCD (`pivot`) | staff | none |
| | Statistiques (`stats`) | staff | none |
| | Fiches de présence (`presence`) | staff | none |
| | Export FFME (`ffme`) | staff | none |
| | Import FFME (`ffme-import`) | admin | none |

## Phase 1 — Mechanism + Compétitions

- `children` in `PAGES` with access/offline helpers; Vitest for `read` / `staffCopy` / `none` and the refused-child
  verdict.
- `router.ts`: nested routes, parent-index redirect (D8), `?section=` redirect; `router.test.ts`.
- `SubNav.vue` (sidebar accordion + phone strip) in `AppShell`; `AppShell.test.ts` (single visible child → nothing
  drawn, offline `none` child disabled).
- Split `CompetitionsPage.vue` into a layout + 4 children (from `BalancePane`, `CoachesPane`, `HelloAssoPane` and the
  list/detail).
- `api/web/pages.py` sub-paths; route tests.
- e2e: selectors of the former `section-*` tabs → sub-menu links; `/bureau/competitions/bilan` opens offline.
- Bump `APP_VERSION` / `VERSION`.

## Phase 2 — Outils

- Children with `meta.keepAlive`; `ffme-import` as an `admin` child.
- `?tab=` redirects; Adhérents links to `/bureau/outils/ffme` and `/bureau/outils/ffme-import`.
- e2e `bureau/test_outils.py`, `bureau/test_adherents.py`.
