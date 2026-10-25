import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { VitePWA } from "vite-plugin-pwa";
import { defineConfig } from "vitest/config";

// One version for the whole app: code_source/VERSION, bumped together with APP_VERSION.
const APP_VERSION = readFileSync(fileURLToPath(new URL("../VERSION", import.meta.url)), "utf8").trim();

// Dev server: FastAPI (uv run dev/run_server.sh) answers everything the Vue app does not serve:
// the API, the runtime configuration, the PWA files, /map, /pivot and the former addresses (redirects).
// The Host header is kept (no changeOrigin) so that the local server's same-origin check accepts the writes.
const BACKEND = process.env.ALJ_BACKEND_URL ?? "http://localhost:8080";
// Office pages (src/router.ts, _SPA_PAGES of api/web/pages.py): served by Vite, not proxied
const SPA_PAGES = ["adherents", "communications", "competitions", "outils", "parametres", "planning"];
const BACKEND_PATHS =
  "^/($|\\?|api/|webhooks/|runtime-config\\.js|sw\\.js|manifest\\.webmanifest|annuaire/|competitions/gestion" +
  `|map($|\\?)|pivot($|\\?)|health|docs|redoc|openapi\\.json|bureau/(?!(${SPA_PAGES.join("|")})($|[/?]))[a-z])`;

export default defineConfig(({ command }) => ({
  // FastAPI serves the built assets under /spa/ (api/web/pages.py); the dev server from its root
  base: command === "build" ? "/spa/" : "/",
  plugins: [
    vue(),
    tailwindcss(),
    // Service worker (src/sw.ts) with the hashed precache list, built into dist/sw.js and served by FastAPI at /sw.js
    // (scope /). The manifest stays served by FastAPI (web/manifest.webmanifest); the app registers the worker itself.
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      manifest: false,
      injectRegister: false,
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        // Built files are served under /spa/, the worker itself from /
        modifyURLPrefix: { "": "/spa/" },
        // Classic script: registered without { type: "module" }, as the former worker
        rollupFormat: "iife",
      },
    }),
  ],
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
