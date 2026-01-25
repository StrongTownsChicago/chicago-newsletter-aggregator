import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mocked } from "vitest";
import type { SupabaseClient } from "@supabase/supabase-js";
import { POST as validateTokenPOST } from "../../pages/api/notifications/validate-unsubscribe-token";
import { POST as getUserPreferencesPOST } from "../../pages/api/notifications/get-user-preferences";
import { POST as unsubscribePOST } from "../../pages/api/notifications/unsubscribe";
import { validateUnsubscribeToken } from "../../lib/unsubscribe-tokens";
import { createMockContext, createMockSupabase } from "../helpers";

describe("Unsubscribe Token Validation", () => {
  it("validates token format and returns null for invalid tokens", () => {
    const secretKey =
      "test-secret-key-for-testing-must-be-at-least-32-chars-long";
    const invalidToken = "invalid-token-string";

    const result = validateUnsubscribeToken(invalidToken, secretKey);
    expect(result).toBeNull();
  });

  it("returns null for empty token", () => {
    const secretKey =
      "test-secret-key-for-testing-must-be-at-least-32-chars-long";
    const result = validateUnsubscribeToken("", secretKey);
    expect(result).toBeNull();
  });

  it("returns null for token with wrong number of parts", () => {
    const secretKey =
      "test-secret-key-for-testing-must-be-at-least-32-chars-long";
    const badToken = "part1.part2"; // Only 2 parts, should be 3
    const result = validateUnsubscribeToken(badToken, secretKey);
    expect(result).toBeNull();
  });
});

describe("Validate Unsubscribe Token API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv(
      "UNSUBSCRIBE_SECRET_KEY",
      "test-secret-key-for-testing-must-be-at-least-32-chars-long",
    );
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("returns 400 if token is missing", async () => {
    const context = createMockContext({ json: {} });
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("Token required");
  });

  it("returns 400 for invalid token", async () => {
    const context = createMockContext({ json: { token: "invalid-token" } });
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toContain("Invalid or expired");
  });

  it("returns 500 if secret key is not configured", async () => {
    vi.unstubAllEnvs();
    const context = createMockContext({ json: { token: "any-token" } });
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(500);

    const body = await response.json();
    expect(body.error).toBe("Server configuration error");
  });
});

describe("Get User Preferences API", () => {
  let mockSupabase: Mocked<SupabaseClient>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabase = createMockSupabase() as Mocked<SupabaseClient>;
  });

  it("returns 400 if user_id is missing", async () => {
    const context = createMockContext({
      json: {},
      locals: { supabase: mockSupabase },
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("User ID required");
  });

  it("returns 404 if user not found", async () => {
    mockSupabase.single.mockResolvedValue({
      data: null,
      error: { message: "Not found" },
    });

    const context = createMockContext({
      json: { user_id: "nonexistent-user" },
      locals: { supabase: mockSupabase },
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(404);

    const body = await response.json();
    expect(body.error).toBe("User not found");
  });

  it("returns enabled status for valid user", async () => {
    mockSupabase.single.mockResolvedValue({
      data: {
        notification_preferences: {
          enabled: true,
          delivery_frequency: "daily",
        },
      },
      error: null,
    });

    const context = createMockContext({
      json: { user_id: "valid-user-123" },
      locals: { supabase: mockSupabase },
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.enabled).toBe(true);
  });

  it("returns false if preferences show disabled", async () => {
    mockSupabase.single.mockResolvedValue({
      data: {
        notification_preferences: {
          enabled: false,
          delivery_frequency: "daily",
        },
      },
      error: null,
    });

    const context = createMockContext({
      json: { user_id: "unsubscribed-user" },
      locals: { supabase: mockSupabase },
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.enabled).toBe(false);
  });
});

describe("Unsubscribe API", () => {
  let mockSupabase: Mocked<SupabaseClient>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabase = createMockSupabase() as Mocked<SupabaseClient>;
  });

  it("returns 400 if user_id is missing", async () => {
    const context = createMockContext({
      json: {},
      locals: { supabase: mockSupabase },
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("User ID required");
  });

  it("updates user preferences to disabled", async () => {
    mockSupabase.eq.mockResolvedValue({ error: null });

    const context = createMockContext({
      json: { user_id: "user-to-unsub" },
      locals: { supabase: mockSupabase },
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(200);

    const body = await response.json();
    expect(body.success).toBe(true);

    // Verify update was called with correct data
    expect(mockSupabase.update).toHaveBeenCalledWith({
      notification_preferences: {
        enabled: false,
        delivery_frequency: "daily",
      },
    });
    expect(mockSupabase.eq).toHaveBeenCalledWith("id", "user-to-unsub");
  });

  it("returns 500 if database update fails", async () => {
    mockSupabase.eq.mockResolvedValue({ error: { message: "Database error" } });

    const context = createMockContext({
      json: { user_id: "user-123" },
      locals: { supabase: mockSupabase },
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(500);

    const body = await response.json();
    expect(body.error).toBe("Failed to unsubscribe");
  });

  it("is idempotent - multiple calls succeed", async () => {
    mockSupabase.eq.mockResolvedValue({ error: null });

    const context = createMockContext({
      json: { user_id: "user-123" },
      locals: { supabase: mockSupabase },
    });

    // First call
    const response1 = await unsubscribePOST(context);
    expect(response1.status).toBe(200);

    // Second call (simulating duplicate request)
    const response2 = await unsubscribePOST(context);
    expect(response2.status).toBe(200);

    const body2 = await response2.json();
    expect(body2.success).toBe(true);
  });
});
