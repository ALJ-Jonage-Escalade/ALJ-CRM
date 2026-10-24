# AGENTS.md

## Commands

- install: `npm install`
- build: `npm run build`
- test: `npm test`
- type check: `npx tsc --noEmit`
- lint: `npm run lint`
- format check: `npx prettier --check .`
- format write: `npx prettier --write .`

## Critical Rules

1. TypeScript strict mode is enabled — no implicit any
2. All exported functions must have explicit return types
3. Use `unknown` instead of `any` when type is genuinely unknown
4. Async functions must either catch errors or propagate them — no fire-and-forget
5. Use ESM imports — no CommonJS require() in .ts files

## Code Style

- Formatter: Prettier (config in .prettierrc)
- Linter: ESLint (config in eslint.config.js)
- Single quotes for strings (Prettier handles this)
- Prefer const over let; avoid var

## Types

- No `as any` casts — use type guards or proper generics
- Prefer interfaces over types for object shapes (mergeable)
- Use types for unions, intersections, and utility types

## Testing

- Framework: Vitest (not Jest unless existing)
- Test files: *.test.ts co-located with source, or tests/
- Mock with vi.mock() — not manual mocks unless necessary
- Use describe/it blocks for grouping; test() for single assertions

## What NOT To Do

- Use require() in TypeScript source files
- Cast with `as any` — use type guards
- Leave unhandled promise rejections
- Write .js files inside src/ — TypeScript only
- Modify package-lock.json manually
