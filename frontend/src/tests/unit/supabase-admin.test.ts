import { describe, it, expect, vi, beforeEach } from "vitest";

describe("getSupabaseAdmin", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("throws error if not in SSR mode", async () => {
    vi.stubEnv("SSR", ""); // Simulate non-SSR

    try {
      await import("../../lib/supabase-admin");
      expect.fail("Should have thrown error");
    } catch (e: unknown) {
      if (e instanceof Error) {
        expect(e.message).toContain("Security Error");
      } else {
        throw e;
      }
    }
  });

  it("throws error if missing environment variables", async () => {
    vi.stubEnv("SSR", "true");
    vi.stubEnv("PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "");

    try {
      const { getSupabaseAdmin } = await import("../../lib/supabase-admin");
      getSupabaseAdmin();
      expect.fail("Should have thrown error");
    } catch (e: unknown) {
      if (e instanceof Error) {
        expect(e.message).toContain("Missing Supabase URL or Service Role Key");
      } else {
        throw e;
      }
    }
  });

  it("initializes successfully with correct environment", async () => {
    vi.stubEnv("SSR", "true");
    vi.stubEnv("PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key");

    const { getSupabaseAdmin } = await import("../../lib/supabase-admin");
    const client = getSupabaseAdmin();
    expect(client).toBeDefined();
  });
});
