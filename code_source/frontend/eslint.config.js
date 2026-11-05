import { globalIgnores } from "eslint/config";
import { defineConfigWithVueTs, vueTsConfigs } from "@vue/eslint-config-typescript";
import pluginVue from "eslint-plugin-vue";
import pluginVitest from "@vitest/eslint-plugin";
import skipFormatting from "@vue/eslint-config-prettier/skip-formatting";

// Official Vue preset (same shape as `npm create vue`), type-aware rules; formatting is left to Prettier
export default defineConfigWithVueTs(
  { name: "app/files-to-lint", files: ["**/*.{ts,mts,vue}"] },
  globalIgnores(["coverage/", "dist/", "src/lib/api-schema.ts"]),
  pluginVue.configs["flat/recommended"],
  vueTsConfigs.recommendedTypeChecked,
  { ...pluginVitest.configs.recommended, files: ["src/**/*.test.ts"] },
  {
    // Mocks: `vi.fn(async () => value)` and `expect(obj.method).toHaveBeenCalled()` are idiomatic in tests
    files: ["src/**/*.test.ts"],
    rules: {
      "@typescript-eslint/require-await": "off",
      "@typescript-eslint/unbound-method": "off",
      // Vitest accepts a failure message: expect(value, message)
      "vitest/valid-expect": ["error", { maxArgs: 2 }],
    },
  },
  skipFormatting,
  {
    // Braces on every if/else/for/while body, even one-liners; after skipFormatting, which turns `curly` off
    name: "app/style",
    rules: { curly: ["error", "all"] },
  },
);
