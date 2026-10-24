import { describe, it, expect, vi } from "vitest";

vi.mock("../../lib/supabase", () => ({ supabase: {}, notificationsEnabled: () => true }));
vi.mock("../../lib/server/supabase-admin", () => ({ getSupabaseAdmin: vi.fn() }));

// A prerendered endpoint would run once at build time, with no visitor, form or cookies.
const routes = import.meta.glob<{ prerender?: boolean }>("../../pages/api/**/*.ts", {
  eager: true,
});

describe("API routes", () => {
  it("finds the routes", () => {
    expect(Object.keys(routes).length).toBeGreaterThan(0);
  });

  it.each(Object.entries(routes))("%s is rendered on each request", (_path, route) => {
    expect(route.prerender).toBe(false);
  });
});
