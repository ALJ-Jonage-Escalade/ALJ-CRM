# Competitors limited to a membership status (« Terminé »)

## Problem
On a competition, the « Ajouter un adhérent » picker and « 🧗 Charger le groupe « Compétition » » offer every
member of the Firestore `adherents` directory, whatever their membership status. Only members whose FFME licence
is confirmed (status « Terminé », the last step of the workflow, `schema_v2.STATUS_PRIORITY`) may compete.

The directory does not carry the status: `sync_adherents_from_main` reads `v_adherents_legacy` (one row per
purchase) and drops `status`. It also writes one document per member from whichever purchase row comes last
(`ORDER BY user_id` only): with several purchases in the season (a cancelled one and a valid one, a waiting list
and a confirmed one), `tarif` / `creneau_groupe` are arbitrary.

## Decisions
- Filter on the API, by a list of statuses: `?status=Terminé` (repeatable: `?status=Terminé&status=Validé`),
  values validated against `api.members.schemas.MemberStatus` (unknown value → 422). No parameter: no filter
  (current behaviour, other callers unchanged).
  - `GET /api/competition-members?status=…`
  - `POST /api/competitions/{id}/load-group?status=…`
- The Vue page owns the list: `COMPETITOR_STATUSES = ["Terminé"]` in `pages/competitions/competitions.ts`, sent on
  both calls. One call for the member list: the filtered list feeds both the participant rows (tariff, slot group,
  e-mail) and the picker. A participant no longer « Terminé » would lose its group / e-mail on the page: accepted,
  a licensed competitor's licence is never cancelled in practice.
- Directory: each member is written from their highest-priority purchase of the season
  (`purchase_priority_score(status, tarif, amount)`, the import's rule; ties: the last row, as before);
  `statut`, `tarif`, `creneau_groupe` all come from that purchase. `statut` is normalized with
  `domain.members.view.normalize_status` (`termine` → `Terminé`).
- Rollout, self-healing: when the server reads the directory from Firestore and a document has no `statut`, the
  projection is marked dirty; the next background tick (≤ 3 min) rewrites it. Until then such a member does not
  match a status filter (strict).
- Server-side enforcement on `POST /participants`: no (offline queue: a status change between queueing and replay
  would reject a write the coach believed done; coaches are trusted).
- Coach-facing texts, built from `COMPETITOR_STATUSES`:
  - hint under the member search: « Adhérents au statut « Terminé » uniquement »
  - empty result: « Aucun adhérent trouvé : seuls les adhérents au statut « Terminé » peuvent être ajoutés (ou il est déjà inscrit). »
  - load-group, nobody added: « ℹ️ Tous les membres « Terminé » du groupe « Compétition » sont déjà présents dans la liste. »
    (keeps « déjà présents », asserted by e2e)

## Changes
1. `infrastructure/firestore/competitions/adherents.py`
   - `sync_adherents_from_main`: keep one row per member (highest `purchase_priority_score`), write `statut`.
   - `_adherent_as_legacy_dict`: expose `statut` (normalized, `""` when missing).
   - `list_adherents(search, competition_only, statuses=None)`: keep members whose `statut` is in `statuses`.
   - `_adherents_raw`: a fresh Firestore read with a document lacking `statut` marks the projection dirty
     (`CloudDatabase`, lazy import).
2. `infrastructure/firestore/competitions/participants.py`: `load_competition_group_doc(competition_id, statuses=None)`
   (and `load_competition_group_into`) pass `statuses` to `list_adherents`.
3. `infrastructure/firestore/cloud_database.py`: `mark_projection_dirty()`.
4. Services and routes: `services/competitions/members.py` `list_members(statuses)`,
   `services/competitions/participants.py` `load_competition_group(competition_id, statuses)`,
   `api/competitions/members.py` and `api/competitions/participants.py` take `status: list[MemberStatus] | None = Query(None)`;
   `CompetitionMember` gains `statut: str = ""`.
5. Contract: `uv run python dev/export_openapi.py`, `npm run gen:api` (commit `openapi.json`, `api-schema.ts`).
6. Frontend:
   - `competitions.ts`: `COMPETITOR_STATUSES`, `competitorStatusesLabel`, `competitionMembersPath()`.
   - `CompetitionsPage.vue`: member list fetched with the status filter.
   - `services/competitions.ts`: `loadGroup(competitionId, statuses)` sends `?status=`.
   - `CompetitionDetail.vue`: texts above, `loadGroup` passes `COMPETITOR_STATUSES`.
7. Dev seed (`dev/seed/seed_emulator.py`): members with a licence are « Terminé », the incomplete ones (no licence)
   stay « Validé » — otherwise the dev / e2e picker is empty.
8. Tests
   - Python: directory sync (status written, highest-priority purchase kept), `list_adherents(statuses=…)`,
     self-heal marks dirty, routes with `?status=` (filter, 422 on unknown value), load-group with a filter.
   - Vitest: `competitionMembersPath`, page fetches with `?status=Terminé`, load-group sends it, texts.
   - e2e: `test_data.members(..., statuses=…)`; the competitors fixtures and the load-group test use « Terminé ».
9. Version bump (`APP_VERSION`, `VERSION`): 2.28.0 → 2.29.0.
