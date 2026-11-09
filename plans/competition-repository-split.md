# Plan — split `CompetitionRepository` into per-domain modules

Desloppify finding `review::.::holistic::abstraction_fitness::competition_repository_inheritance_chain`, left open in
batch 5 because of its size. Inventory below taken on 2026-11-09 (branch `feat/deslopify-batch-6`, 2.50.0); check it
again before starting (`grep` commands in § Checks).

## Problem

`infrastructure/firestore/competition_repository.py` exposes one class, `CompetitionRepository`, built from
"mixins" that are in fact a chain of layered classes:

```
CompetitionStoreBase                       competitions/base.py           16 methods, all private + COLLECTION_* constants
├── MemberDirectoryMixin                   competitions/adherents.py      14 methods (5 public) + directory cache state
│   ├── CompetitionsMixin                  competitions/competitions.py   18 methods (14 public)
│   └── ParticipantsMixin                  competitions/participants.py   21 methods (17 public)
│       └── HelloAssoItemsMixin            competitions/helloasso_items.py 19 methods (15 public)
└── CoachesMixin                           competitions/coaches.py         6 methods (4 public)
```

About 94 methods behind one name (1,620 lines). A call such as `Repo.save_coach` does not say which module owns it,
a mixin cannot be used alone, and the class docstring admits the shape is kept "for test patching", not for the domain.

## Target

Plain function modules, one per domain, with no class and no `cls.` lookups:

| Module (`infrastructure/firestore/competitions/`) | Contents |
|---|---|
| `documents.py` (from `base.py`) | collection names, `now_iso`/`now_display`, `new_id`, `with_retries`, document ↔ `Competition` conversion (`build_comp_doc`, `comp_from_doc`, `api_doc`, `clean_doc`), `load_comp_doc`, `list_comp_docs`, `save_parts`, `row_stamp`, `recompute_counters`, coach name helpers |
| `member_directory.py` (from `adherents.py`) | `rebuild_member_directory`, `list_members`, `directory_outdated`, the `adherents` cache (module-level `TimedCache` + last read + heal flags) |
| `competitions.py` | competition CRUD, archive, `get_bilan`, `season_of_date` |
| `participants.py` | participant rows of a competition, payments, results, `ParticipantAlreadyPaid`, `ParticipantChanged`, `RowGuard` |
| `helloasso_items.py` | HelloAsso mirror, links, `ItemAlreadyLinked` |
| `coaches.py` | coach CRUD |

Callers import the module they need: `from infrastructure.firestore.competitions import coaches` then
`coaches.save_coach(...)`. `competition_repository.py` and `CompetitionRepository` are deleted at the end.

## Status

Done in desloppify batch 7 (branch `feat/deslopify-batch-7`, 2.51.0). Owner answers (2026-11-09): Q1 functions,
Q2 one commit per domain in one PR, Q3 delete, Q4 rename. Besides the Q3 list, the boolean wrappers of the
`*_doc` writes (`remove_participant`, `record_manual_payment`), `season_of_date` (only used by `get_bilan`) and
`list_mirror_items` (folded into `list_unlinked_items`) went too.

## Decisions to take before starting (owner)

| # | Question | Proposal |
|---|---|---|
| Q1 | Module-level functions, or one small class per domain (`Coaches.save(...)`)? | Functions (what the finding asks; no state except the directory cache) |
| Q2 | Migrate in one batch or one domain per PR? | One domain per commit, one PR; the facade stays until the last commit so every commit is green |
| Q3 | Delete the methods with no production caller (list below) or keep them? | Delete, with their tests, after a last `grep` |
| Q4 | Rename while moving (`adherents.py` → `member_directory.py`, `base.py` → `documents.py`)? | Yes, the module names then say what they hold |

## Dependencies between domains (today's `cls.` lookups)

These become plain imports; the graph must stay acyclic:

- `adherents` → `base`
- `coaches` → `base`
- `competitions` → `base`, `adherents` (`_adherent_map`, `_adherents_raw`, `_sex_code`)
- `participants` → `base`, `adherents` (`_adherent_map`, `list_members`)
- `helloasso_items` → `base`, `adherents` (`_adherent_map`, `list_members`), `participants` (`_mutate_participants`,
  `_new_participant`, `_update_participant`)

So the migration order is: `base` → `adherents` → `coaches` → `competitions` → `participants` → `helloasso_items`.
The private helpers used across modules (`_adherent_map`, `_mutate_participants`, …) become public functions of
their module, without the underscore.

## Callers (production)

From `grep` on method names (also matches same-named service methods, e.g. `Service.list_coaches`; check each hit):

- **services/competitions/**: `store.py` (`get_competition_doc`), `coaches.py`, `competitions.py`, `participants.py`,
  `members.py`, `helloasso_items.py`, `helloasso_webhook.py`, `all_paid_notification.py`, `results_batch.py`
- **services/communications/email_dispatch.py** (`get_competition_doc`, `list_members`)
- **services/members/members.py** (`list_competitions`, `list_members`)
- **infrastructure/firestore/cloud_database.py** (`rebuild_member_directory`, `directory_outdated`)
- **domain/competitions/matching.py**: only its docstring names `list_participants` (update the wording)
- dev / scripts: `dev/seed/seed_emulator.py`, `dev/seed/mycompet_state.py`, `scripts/migrate_gender_to_sex.py`,
  `e2e/helpers/data.py` (`set_selection`)

## Public methods without a production caller (Q3)

Only used by tests (`tests/infrastructure/firestore/test_competition_repository.py` unless noted):
`count_adherents`, `list_planning_groups`, `get_bilan`, `list_competitions_for_coach`, `clear_item_link`,
`save_item_comment`, `load_competition_group_into`, `mark_cancelled` (also `tests/api/competitions/test_helloasso_items.py`,
`tests/services/competitions/test_helloasso_webhook_payments.py`), `set_payment_status` (also
`tests/api/competitions/test_participants.py`, `test_offline_queue.py`), `set_selection` (also `test_offline_queue.py`,
`e2e/helpers/data.py`, `e2e/test_offline.py`). Used internally only: `season_of_date`, `set_competition_status`,
`list_mirror_items`. Test-only setters may be kept as test fixtures' helpers instead of production code.

## Tests

- 35 files import the facade (15 in `src/`, 4 dev/scripts/e2e, 16 tests).
- `tests/support/fake_firestore.py` resets the directory cache through `CompetitionRepository._invalidate_adherents_cache()`
  and reads `COLLECTION_ADHERENTS`; `tests/support/api_case.py` reads `get_competition_doc`. Point them at the new
  modules first, since every Firestore test goes through them.
- Patches of the facade (`patch.object(Repo, …)`, `patch(f"{Repo}.…")`): about 24 sites in 8 files —
  `tests/infrastructure/firestore/test_competition_repository.py`, `tests/services/test_services.py`,
  `tests/services/competitions/test_helloasso_webhook_payments.py`, `test_results_batch_run.py`,
  `tests/api/competitions/test_members.py`, `test_results.py`, `test_competitions.py`,
  `tests/api/integrations/test_helloasso_sync.py`. A function patched where it is defined is not seen by a module that
  did `from … import name`: callers should import the module (`from …competitions import coaches`) so patches on
  `coaches.save_coach` keep working.
- `tests/infrastructure/firestore/test_competition_repository.py` follows the split: one test file per new module
  (`tests/infrastructure/firestore/competitions/test_<module>.py`).

## Steps (one commit each, suite green after each)

1. `base.py` → `documents.py` as functions; the mixins call them (facade unchanged).
2. `adherents.py` → `member_directory.py` (cache as module state); update `cloud_database.py`, test support.
3. `coaches.py`, then `competitions.py`, `participants.py`, `helloasso_items.py`: functions, callers and patches
   moved domain by domain; the facade keeps delegating until its last user is gone.
4. Delete `competition_repository.py`, the facade and the `*Mixin` classes; remove the dead methods (Q3).
5. ARCHITECTURE.md § 2 (the `competition_repository.py` line), mypy `files` list for the new fully typed modules,
   resolve the desloppify finding.

## Checks

```bash
cd code_source
grep -rn "CompetitionRepository\|competition_repository" src tests dev scripts e2e   # must end empty
grep -rn "cls\." src/infrastructure/firestore/competitions                                  # must end empty
uv run ruff check src tests && uv run mypy && uv run pytest tests
python -m pytest -c e2e/pytest.ini e2e -n 1        # competitions, payments and offline queue flows
```

No behaviour, Firestore document shape or API contract change is expected: `uv run python dev/export_openapi.py --check`
must pass untouched.
