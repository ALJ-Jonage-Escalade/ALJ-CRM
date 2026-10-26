# AGENTS.md — Vue frontend

Vue 3 + Vite + TypeScript app of every office screen (`/bureau/...`), built into `dist/` and served by FastAPI under `/spa/`.
Plan: `plans/vue-responsive-frontend.md` · decisions: `documentations/plan_frontend_vue.md` · project rules: `../../AGENTS.md`.
All commands run from `code_source/frontend/`, Node version from `.nvmrc`.

## Commands

- install: `npm ci` (add a dependency: `npm install --save-exact <pkg>`, MIT or equivalent license only, decision D5)
- dev: `npm run dev` → http://localhost:5173/bureau/, next to `uv run dev/run_server.sh` in `code_source/` (Vite proxies
  the API and the PWA files to :8080)
- all checks (as CI): `npm run check:api && npm run lint && npm run format:check && npm run typecheck && npm test && npm run build`
- typecheck: `npm run typecheck` (vue-tsc, also checks `.vue` files; not `npx tsc`)
- format: `npm run format` before committing (Prettier, width 140, enforced in CI)
- lint: `npm run lint` (zero warnings); `npm run lint -- --fix` fixes most issues, missing braces included

## API contract

- `openapi.json` and `src/lib/api-schema.ts` are generated, never edit them by hand: after a server model change, run
  `uv run python dev/export_openapi.py` in `code_source/`, then `npm run gen:api` here, and commit both
- Pages call the API through the services of `src/services/` (below), never `client.GET/POST/...` directly; body types
  come from `Schemas["ModelName"]`, not hand-written interfaces
- No runtime schema library (no Zod): the types come from the contract, forms use plain validation functions

## API services

- One file per server theme, mirroring `src/api/<theme>/` on the server: `src/services/<theme>.ts` exports
  `create<Theme>Api(client)`, e.g. `createCompetitionsApi`. A new route goes in the service of its server theme
- A component injects the client once and names each service after it:
  `const competitionsApi = createCompetitionsApi(inject(CLIENT_KEY)!)`, then `await competitionsApi.archivePast()`
- A method takes what the page knows (ids, values, `Schemas[...]` bodies) and returns the answer's body, unwrapped
  (throws an `ApiError`, `lib/client.ts`); paths, query parameters and fixed request values (`club: "JONAGE"`,
  `selectionne: true`) stay in the service. File exports (`parseAs: "blob"`) return the call itself, for `saveExport()`
- Messages, confirmations and error display stay in the page; the return type of `create<Theme>Api` is inferred (the
  contract's answer types)

## Layout

- `src/pages/` one component per route (`router.ts`, every route declares `meta.access`, see `lib/access.ts`);
  page parts in `src/pages/<page>/`
- `src/components/` shared components; `src/components/ui/` the `Ui*` building blocks (buttons, dialogs, panels;
  reka-ui underneath)
- `src/composables/` state and side effects (`useX()`); `useSyncedResource` for data polled from the API and kept offline
- `src/lib/` plain TypeScript (no Vue components): API client, roles, IndexedDB store, CSV, downloads
- `src/services/` the API calls, one file per server theme (see API services)
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
