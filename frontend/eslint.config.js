import { defineConfig } from "eslint/config";
import eslintPluginAstro from "eslint-plugin-astro";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import tseslint from "typescript-eslint";

export default defineConfig(
  { ignores: ["dist/**", ".astro/**", ".wrangler/**", "coverage/**", "playwright-report/**", "test-results/**"] },
  ...tseslint.configs.recommended,
  ...eslintPluginAstro.configs.recommended,
  // Type-aware rules cover .ts only: astro-eslint-parser can't use projectService and
  // crashes under the type-checked set. .astro files (and their <script> blocks,
  // linted as virtual *.astro/*.ts files) keep the untyped recommended rules.
  {
    files: ["**/*.ts"],
    ignores: ["**/*.astro/*.ts"],
    extends: [tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
    },
  },
  {
    plugins: { "no-unsanitized": noUnsanitized },
    rules: {
      ...noUnsanitized.configs.recommended.rules,
      eqeqeq: ["error", "smart"],
      "no-var": "error",
      "prefer-const": "error",
      // newsletter raw_html is rendered with set:html; every use needs a written reason
      "astro/no-set-html-directive": "error",
    },
  },
  {
    files: ["src/**/*.{ts,astro}"],
    ignores: ["src/pages/api/**", "src/lib/supabase-admin.ts", "src/tests/**"],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [{
          group: ["**/supabase-admin", "**/supabase-admin.ts"],
          message: "supabase-admin carries the service key: import it only from src/pages/api/** server routes.",
        }],
      }],
    },
  },
  // Mocks are deliberately loose: partial `any` doubles, async stubs that never await,
  // and `expect(obj.method)` assertions on mocked methods.
  {
    files: ["src/tests/**/*.ts"],
    rules: {
      "@typescript-eslint/no-unsafe-argument": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-return": "off",
      "@typescript-eslint/require-await": "off",
      "@typescript-eslint/unbound-method": "off",
    },
  },
  // FormDataEntryValue.toString() turns a File into "[object File]". These routes only
  // receive text fields from their own forms; narrowing to strings would change how a
  // forged File is handled, so it waits for a deliberate change. Remove files as they are fixed.
  {
    files: [
      "src/pages/api/auth/signin.ts",
      "src/pages/api/auth/signup.ts",
      "src/pages/api/notifications/create-rule.ts",
      "src/pages/api/notifications/delete-rule.ts",
      "src/pages/api/notifications/update-rule.ts",
    ],
    rules: { "@typescript-eslint/no-base-to-string": "off" },
  },
);
