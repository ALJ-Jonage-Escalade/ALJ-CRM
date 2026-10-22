import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

// One version for the whole app: code_source/VERSION, bumped together with APP_VERSION.
const APP_VERSION = readFileSync(fileURLToPath(new URL("../VERSION", import.meta.url)), "utf8").trim();

// Dev server: FastAPI (uv run dev/run_server.sh) answers everything the Vue app does not serve yet:
// the API, the runtime configuration, the PWA files and the pages not migrated. The Host header is
// kept (no changeOrigin) so that the local server's same-origin check accepts the writes.
const BACKEND = process.env.ALJ_BACKEND_URL ?? "http://localhost:8080";
// Office pages already migrated (src/router.ts, _SPA_PAGES of api/web/pages.py): served by Vite, not proxied
const SPA_PAGES = ["communications", "parametres"];
const BACKEND_PATHS =
  "^/($|\\?|api/|webhooks/|runtime-config\\.js|sw\\.js|manifest\\.webmanifest|static-web/|annuaire/|competitions|index($|\\?)" +
  `|map($|\\?)|pivot($|\\?)|health|docs|redoc|openapi\\.json|bureau/(?!(${SPA_PAGES.join("|")})($|[/?]))[a-z])`;

export default defineConfig(({ command }) => ({
  // FastAPI serves the built assets under /spa/ (api/web/pages.py); the dev server from its root
  base: command === "build" ? "/spa/" : "/",
  plugins: [vue(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(APP_VERSION) },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { [BACKEND_PATHS]: { target: BACKEND } },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
}));
