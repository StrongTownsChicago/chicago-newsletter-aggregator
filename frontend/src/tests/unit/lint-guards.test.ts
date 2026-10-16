// @vitest-environment node
import path from "node:path";
import { ESLint } from "eslint";
import { beforeAll, describe, expect, it } from "vitest";

const FRONTEND_ROOT = path.resolve(__dirname, "../../..");
const GUARD_RULES = new Set(["no-restricted-imports", "no-restricted-syntax"]);

// Real files, so the type-aware parser finds them in the project; only their text is replaced.
const OUTSIDE_API = "src/lib/form-data.ts";
const API_ROUTE = "src/pages/api/auth/signin.ts";

const eslint = new ESLint({
  cwd: FRONTEND_ROOT,
  ruleFilter: ({ ruleId }) => GUARD_RULES.has(ruleId),
});

async function guardViolations(code: string, filePath: string): Promise<number> {
  const [result] = await eslint.lintText(code, { filePath: path.join(FRONTEND_ROOT, filePath) });
  return result.messages.filter((message) => GUARD_RULES.has(message.ruleId ?? "")).length;
}

// The first lint builds the TypeScript program, which takes several seconds.
beforeAll(async () => {
  await eslint.lintFiles([OUTSIDE_API]);
}, 60_000);

const adminImports = {
  static: 'export { supabaseAdmin } from "./supabase-admin";\n',
  dynamic: 'export const load = () => import("./supabase-admin");\n',
  template: "export const load = () => import(`./supabase-admin`);\n",
};

describe("supabase-admin import guard", () => {
  it.each(Object.entries(adminImports))("flags a %s import outside API routes", async (_, code) => {
    expect(await guardViolations(code, OUTSIDE_API)).toBe(1);
  });

  it.each(Object.entries(adminImports))("allows a %s import in API routes", async (_, code) => {
    expect(await guardViolations(code, API_ROUTE)).toBe(0);
  });

  it("allows other dynamic imports", async () => {
    expect(await guardViolations('export const load = () => import("./supabase");\n', OUTSIDE_API)).toBe(0);
  });
});

describe("computed import.meta.env reads", () => {
  const computedRead = 'const name = "X";\nexport const value: unknown = import.meta.env[name];\n';

  it.each([OUTSIDE_API, API_ROUTE])("are flagged in %s", async (filePath) => {
    expect(await guardViolations(computedRead, filePath)).toBe(1);
  });
});
