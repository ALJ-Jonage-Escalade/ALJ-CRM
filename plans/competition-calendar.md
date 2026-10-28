# Competition calendar

## Problem
The Compétitions page's calendar view (`frontend/src/pages/competitions/CompetitionCalendar.vue`) is hand-made in
the component: three near-identical padding loops build the month grid, nothing is tested (neither
`CompetitionsPage.test.ts` nor e2e mention it), a multi-day competition is repeated as one chip per day, the legend is
hard-coded and misses « combiné », a second discipline palette (`DISCIPLINE_BG`) disagrees with `disciplineColor()`,
a phone gets 7 columns of ~50 px, and the component both emits `open` and calls `router.push`.
It is fed `current` (`CompetitionsPage.vue`), which applies the season and « À venir / Passées » filters and drops
archived competitions: navigating months shows empty grids without explanation.

## Decisions
- Scope: the competition calendar only. The Planning week grid (`planning/WeekGrid.vue` + `slots.ts`) stays as it
  is: it shows a weekly template (day names, free-text hours, no dates), not dated events; no shared calendar
  component. The competition calendar follows its pattern: pure tested layout functions, a thin drawing component.
- No library: FullCalendar and Schedule-X are open core (the vendor risk that dropped PrimeVue, D5), vue-cal has a
  single maintainer and its own CSS, Reka's `Calendar` is a date picker. Not needed: drag and drop, resize, week/day
  views.
- Multi-day competitions: one bar across the days, Google Calendar style. Each week row lays its bars in lanes
  (first free lane, as `layoutDay` in `slots.ts`); a bar crossing a week boundary continues on the next row with a
  ‹ / › marker.
- Busy days: the week row grows to fit every lane; no cap, no « +N autres » (a few dozen competitions a season).
- Bar: name (truncated), continuation markers, `title` = name · place · dates; archived competitions greyed (lower
  opacity, slate); the selected competition (`?id=`) ringed.
- Phones (`< md`): an agenda list of the month instead of the grid (same month and arrows): `sam. 15 – dim. 16 · Nom ·
  Lieu`, discipline colour dot, today marked. Grid from `md` up. Both from the same computed data.
- Data: the search applies; the « Toutes / À venir / Passées » and season filters do not, and are hidden in calendar
  view (the month arrows replace them); archived competitions included, greyed.
- Opening month: the month of the selected competition (`?id=`) when there is one, otherwise today's.
- Colours: one source, `disciplineColor()` and the `BadgeColor` palette. `SOFT` / `SOLID` move from `UiBadge.vue` to
  `components/ui/palette.ts`, used by the badges and the bars; `DISCIPLINE_BG` removed. Legend generated from
  `DISCIPLINE_COLOR` plus « Autre / non précisé ». No discipline (`discipline()` returns `""`) → slate in the calendar
  (blue is difficulté); badges unchanged.
- The component only emits `open(competition)`; the page does `router.push({ query: { id } })` and goes back to the
  cards. No router in the component.
- The displayed month stays local state, not in the URL (the view mode is not in the URL either; putting it there is a
  page-wide change of its own).
- Dates are local `YYYY-MM-DD` strings, never `toISOString()` (UTC shifts the day on French evenings); month and day
  names through `Intl.DateTimeFormat("fr-FR")`, not hand-written arrays.
- Offline: rendering only uses the competitions already loaded; nothing new to fetch.

## Changes
1. `frontend/src/pages/competitions/calendar.ts` (new, pure):
   - `monthWeeks(year, month)` → week rows, Monday first, with the neighbouring months' days (`dateIso`, `dayNumber`,
     `inMonth`, `isToday`).
   - `layoutWeek(competitions, weekStartIso)` → `{ competition, startCol, span, lane, continuesBefore, continuesAfter }[]`
     and the row's lane count. A missing `date_fin`, or one before the start, means a single day; no start date → left out.
   - `monthAgenda(competitions, year, month)` → the month's competitions overlapping it, by start date then name.
   - `initialMonth(selected, today)`, `shiftMonth({ year, month }, delta)`.
2. `frontend/src/pages/competitions/calendar.test.ts` (new, Vitest): months starting on Monday and on Sunday, February of
   a leap year, a competition crossing a week and a month boundary, missing / inverted `date_fin`, three overlapping
   competitions on three lanes, agenda order, `initialMonth` with and without a selection.
3. `frontend/src/components/ui/palette.ts` (new): `SOFT`, `SOLID` moved from `UiBadge.vue` (which imports them).
4. `frontend/src/pages/competitions/CompetitionCalendar.vue`: rewritten as drawing only — toolbar (month title,
   Aujourd'hui, Précédent / Suivant), generated legend, week rows as CSS grids (row 1 the day numbers, one row per lane, the
   day cells spanning every row; no absolute positioning) from `md` up,
   agenda list below `md`; props `competitions`, `selectedId`; emits `open`. Keep the `data-testid`s
   (`comp-calendar`, `calendar-title`, `prev-month`, `next-month`, `calendar-day`, `calendar-comp-chip`) and add
   `calendar-agenda`.
5. `frontend/src/pages/CompetitionsPage.vue`: feed the calendar with the search-filtered competitions, archived
   included; hide the « when » and season filters in calendar view; on `open`, `router.push` and back to the cards.
6. `frontend/src/pages/CompetitionsPage.test.ts`: a competition shows as a bar on its days, clicking it sets `?id=`
   and shows the cards, an archived competition is shown greyed, the « when » filter is hidden in calendar view.

## Checks
`cd code_source/frontend && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`;
by hand at 375 px and desktop widths with the seeded emulator data (a multi-day competition crossing a Sunday).
No API change. Functional change: bump `APP_VERSION` (`src/domain/constants.py`) and `code_source/VERSION` together.
