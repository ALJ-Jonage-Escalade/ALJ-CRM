# AGENTS.md — Vue frontend

Vue 3 + Vite + TypeScript app of every office screen (`/bureau/...`), built into `dist/` and served by FastAPI under `/spa/`.
Plan: `plans/vue-responsive-frontend.md` · decisions: `documentations/plan_frontend_vue.md` · project rules: `../../AGENTS.md`.
All commands run from `code_source/frontend/`, Node version from `.nvmrc`.

## Commands

- install: `npm ci` (add a dependency: `npm install --save-exact <pkg>`, MIT or equivalent license only, decision D5)
- dev: `npm run dev` → http://localhost:5173/bureau/, next to `uv run dev/run_server.sh` in `code_source/` (Vite proxies
  the API, `/map`, `/pivot` and the PWA files to :8080)
- all checks (as CI): `npm run check:api && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`
- typecheck: `npm run typecheck` (vue-tsc, also checks `.vue` files; not `npx tsc`)
- format: `npm run format` before committing (Prettier, width 140, enforced in CI)
- lint: `npm run lint` (zero warnings); `npm run lint -- --fix` fixes most issues, missing braces included

## API contract

- `openapi.json` and `src/lib/api-schema.ts` are generated, never edit them by hand: after a server model change, run
  `uv run python dev/export_openapi.py` in `code_source/`, then `npm run gen:api` here, and commit both
- Pages call the API through the typed client (`src/lib/client.ts`, injected with `CLIENT_KEY`); body types come from
  `Schemas["ModelName"]`, not hand-written interfaces
- No runtime schema library (no Zod): the types come from the contract, forms use plain validation functions

## Layout

- `src/pages/` one component per route (`router.ts`, every route declares `meta.access`, see `lib/access.ts`);
  page parts in `src/pages/<page>/`
- `src/components/` shared components; `src/components/ui/` the `Ui*` building blocks (buttons, dialogs, panels;
  reka-ui underneath)
- `src/composables/` state and side effects (`useX()`); `useSyncedResource` for data polled from the API and kept offline
- `src/lib/` plain TypeScript (no Vue components): API client, roles, IndexedDB store, CSV, downloads
- No global store (no Pinia): shared services are provided in `main.ts` (`provide(KEY, value)`) and injected

## Code style

- `<script setup lang="ts">`, Composition API only; styling with Tailwind classes in the template
- Prettier style: double quotes, semicolons, trailing commas; braces on every `if`/`else`/loop body (ESLint `curly`)
- Strict TypeScript (`noUncheckedIndexedAccess`): no `any`, no `as` casts to silence an error, no `!` unless the value
  is guaranteed; prefer `satisfies` and type guards
- Exported functions declare their return type
- Promises are awaited, returned or explicitly discarded with `void` (type-aware lint rules)
- UI text in French, code, comments and identifiers in English
- A file starts with a short comment saying what it is for when that is not obvious from its name

## Tests

- Vitest + Vue Test Utils, jsdom; `src/**/*.test.ts` next to the module tested
- Fake the services by providing them (`CLIENT_KEY`, `API_KEY`, `AUTH_KEY`...) rather than with `vi.mock()`
- Select elements by `data-testid`, not by CSS classes or text layout
- Use `flushPromises()` after an action that triggers API calls

## Do not

- Commit `dist/` or `node_modules/`, or edit `package-lock.json` by hand
- Hardcode the backend URL or production settings: runtime configuration comes from the server (`lib/runtime.ts`)
