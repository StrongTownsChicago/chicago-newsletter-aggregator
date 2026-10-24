import { defineConfig } from "eslint/config";
import eslintPluginAstro from "eslint-plugin-astro";
import noUnsanitized from "eslint-plugin-no-unsanitized";
import tseslint from "typescript-eslint";

/** Code lines per file: blank lines and comments don't count. */
const maxLines = (max) => ({
  "max-lines": ["error", { max, skipBlankLines: true, skipComments: true }],
});

const computedEnvRead = {
  selector: "MemberExpression[computed=true] > MemberExpression.object[object.type='MetaProperty'][property.name='env']",
  message: "Read import.meta.env.NAME literally: the build drops server-only variables from computed reads.",
};

const supabaseAdminMessage =
  "supabase-admin carries the service key: import it only from src/pages/api/** server routes.";

export default defineConfig(
  { ignores: ["dist/**", ".astro/**", ".wrangler/**", "coverage/**", "playwright-report/**", "test-results/**", "reports/**", ".stryker-tmp/**"] },
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
      "no-restricted-syntax": ["error", computedEnvRead],
    },
  },
  {
    files: ["src/**/*.{ts,astro}"],
    ignores: ["src/pages/api/**", "src/lib/server/supabase-admin.ts", "src/tests/**"],
    rules: {
      "no-restricted-imports": ["error", {
        patterns: [{
          group: ["**/supabase-admin", "**/supabase-admin.ts"],
          message: supabaseAdminMessage,
        }],
      }],
      // Catches import("…/supabase-admin") and import(`…/supabase-admin`). ESLint replaces a
      // rule set again in a later block rather than merging it, so the shared selector is repeated here.
      "no-restricted-syntax": ["error", computedEnvRead, {
        selector: "ImportExpression > :matches(Literal[value=/supabase-admin/], TemplateLiteral:has(TemplateElement[value.raw=/supabase-admin/])).source",
        message: supabaseAdminMessage,
      }],
    },
  },
  // New files stay under the cap; one that outgrows it is split.
  { files: ["src/**/*.{ts,astro}", "e2e/**/*.ts"], rules: maxLines(400) },
  // No file has its own ceiling: one over the cap is split, not exempted.
  // src/tests/unit/lint-budgets.test.ts fails if a per-file ceiling is added.
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
);
