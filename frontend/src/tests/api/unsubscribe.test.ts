import { describe, it, expect, vi, beforeEach } from "vitest";
import type { Mock } from "vitest";
import { POST as validateTokenPOST } from "../../pages/api/notifications/validate-unsubscribe-token";
import { POST as getUserPreferencesPOST } from "../../pages/api/notifications/get-user-preferences";
import { POST as unsubscribePOST } from "../../pages/api/notifications/unsubscribe";
import { createMockContext } from "../helpers";

const { mockSupabaseAdmin } = vi.hoisted(() => {
  return {
    mockSupabaseAdmin: {
      from: vi.fn(() => ({
        select: vi.fn(() => ({
          eq: vi.fn(() => ({
            single: vi.fn(),
          })),
        })),
        update: vi.fn(() => ({
          eq: vi.fn(),
        })),
      })),
    },
  };
});

vi.mock("../../lib/supabase-admin", () => ({
  getSupabaseAdmin: vi.fn(() => mockSupabaseAdmin),
}));

vi.mock("jose", () => ({
  jwtVerify: vi.fn(),
}));

import { jwtVerify } from "jose";
const mockedJwtVerify = vi.mocked(jwtVerify);

describe("Validate Unsubscribe Token API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv(
      "UNSUBSCRIBE_SECRET_KEY",
      "test-secret-key-for-testing-must-be-at-least-32-chars-long",
    );
    vi.stubEnv("PUBLIC_SUPABASE_URL", "https://test.supabase.co");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key");
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("returns 400 if token is missing", async () => {
    const context = createMockContext({ json: {} });
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("Token required");
  });

  it("returns 200 with user_id for valid token", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-123", type: "unsubscribe" },
      protectedHeader: { alg: "HS256" },
    });

    const context = createMockContext({ json: { token: "valid-jwt" } });
    const response = await validateTokenPOST(context);

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.user_id).toBe("user-123");
  });

  it("returns 400 for invalid token signature", async () => {
    mockedJwtVerify.mockRejectedValue(new Error("Invalid signature"));

    const context = createMockContext({ json: { token: "invalid-token" } });
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(400);

    const body = await response.json();
    expect(body.error).toBe("Invalid or expired token");
  });

  it("returns 400 for wrong token type", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-123", type: "access" }, // Wrong type
      protectedHeader: { alg: "HS256" },
    });

    const context = createMockContext({ json: { token: "valid-jwt" } });
    const response = await validateTokenPOST(context);

    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.error).toBe("Invalid token type");
  });

  it("returns 400 for missing sub claim", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { type: "unsubscribe" }, // No sub
      protectedHeader: { alg: "HS256" }
    });
    
    const context = createMockContext({ json: { token: "valid-jwt" } });
    const response = await validateTokenPOST(context);
    
    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.error).toBe("Invalid token payload");
  });

  it("returns 400 for malformed request body", async () => {
    const context = createMockContext({ json: null });
    // Mock request.json() to throw
    (context.request.json as Mock).mockRejectedValue(new Error("JSON error"));
    
    const response = await validateTokenPOST(context);
    expect(response.status).toBe(400);
    const body = await response.json();
    expect(body.error).toBe("Invalid request");
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
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv(
      "UNSUBSCRIBE_SECRET_KEY",
      "test-secret-key-for-testing-must-be-at-least-32-chars-long",
    );
    vi.stubEnv("PUBLIC_SUPABASE_URL", "https://test.supabase.co");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key");
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("returns 400 if invalid token provided", async () => {
    mockedJwtVerify.mockRejectedValue(new Error("Invalid token"));

    const context = createMockContext({
      json: { token: "invalid-token" },
      locals: {},
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Invalid token" });
  });

  it("returns 500 if secret key is not configured for token flow", async () => {
    vi.unstubAllEnvs();
    const context = createMockContext({
      json: { token: "any-token" },
      locals: {},
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Server error" });
  });

  it("returns 403 if authenticated user tries to access another user's preferences", async () => {
    const context = createMockContext({
      json: { user_id: "other-user" },
      locals: { user: { id: "current-user" } },
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "Unauthorized" });
  });

  it("returns 500 for malformed request body", async () => {
    const context = createMockContext({ json: null });
    (context.request.json as Mock).mockRejectedValue(new Error("JSON error"));
    
    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Server error" });
  });

  it("returns 401 if no auth and no token", async () => {
    const context = createMockContext({
      json: { user_id: "some-user" },
      locals: {},
    });

    const response = await getUserPreferencesPOST(context);
    expect(response.status).toBe(401);
  });

  it("returns enabled status for valid token", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-123", type: "unsubscribe" },
      protectedHeader: { alg: "HS256" },
    });

    // Mock DB response
    const mockSingle = vi.fn().mockResolvedValue({
      data: { notification_preferences: { enabled: true } },
      error: null,
    });
    const mockEq = vi.fn().mockReturnValue({ single: mockSingle });
    const mockSelect = vi.fn().mockReturnValue({ eq: mockEq });
    (mockSupabaseAdmin.from as unknown as Mock).mockReturnValue({
      select: mockSelect,
    });

    const context = createMockContext({
      json: { token: "valid-token" },
      locals: {},
    });

        const response = await getUserPreferencesPOST(context);
        expect(response.status).toBe(200);
    
        const body = await response.json();
        expect(body.enabled).toBe(true);
        
        // Verify admin client was used with correct user_id
        expect(mockEq).toHaveBeenCalledWith("id", "user-123");
      });
    
      it("returns 400 if user not identified in get-user-preferences", async () => {
        const context = createMockContext({
          json: {}, // No token, no user_id, no auth
          locals: {},
        });
    
        const response = await getUserPreferencesPOST(context);
        expect(response.status).toBe(401); // Strategy 3 catch-all
      });
    
      it("returns 404 if user not found in admin query", async () => {
        mockedJwtVerify.mockResolvedValue({
          payload: { sub: "missing-user", type: "unsubscribe" },
          protectedHeader: { alg: "HS256" }
        });
        
        const mockSingle = vi.fn().mockResolvedValue({
          data: null,
          error: { message: "Not found" }
        });
        const mockEq = vi.fn().mockReturnValue({ single: mockSingle });
        const mockSelect = vi.fn().mockReturnValue({ eq: mockEq });
        (mockSupabaseAdmin.from as unknown as Mock).mockReturnValue({ select: mockSelect });
    
        const context = createMockContext({
          json: { token: "valid-token" },
          locals: {},
        });
    
        const response = await getUserPreferencesPOST(context);
        expect(response.status).toBe(404);
        expect(await response.json()).toEqual({ error: "User not found" });
      });
    });
    describe("Unsubscribe API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv(
      "UNSUBSCRIBE_SECRET_KEY",
      "test-secret-key-for-testing-must-be-at-least-32-chars-long",
    );
    vi.stubEnv("PUBLIC_SUPABASE_URL", "https://test.supabase.co");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key");
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("returns 400 if token is missing", async () => {
    const context = createMockContext({
      json: {},
      locals: {},
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Token required" });
  });

  it("returns 500 if secret key is not configured", async () => {
    vi.unstubAllEnvs();
    const context = createMockContext({ json: { token: "any-token" } });
    const response = await unsubscribePOST(context);
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Server error" });
  });

  it("returns 400 for invalid token type", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-123", type: "wrong" },
      protectedHeader: { alg: "HS256" }
    });
    
    const context = createMockContext({ json: { token: "valid-jwt" } });
    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Invalid token type" });
  });

  it("returns 400 for invalid JWT signature in unsubscribe", async () => {
    mockedJwtVerify.mockRejectedValue(new Error("Invalid signature"));
    
    const context = createMockContext({ json: { token: "invalid-token" } });
    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Invalid or expired token" });
  });

  it("returns 400 for missing sub claim", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { type: "unsubscribe" },
      protectedHeader: { alg: "HS256" }
    });
    
    const context = createMockContext({ json: { token: "valid-jwt" } });
    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "Invalid token payload" });
  });

  it("returns 500 for malformed request body", async () => {
    const context = createMockContext({ json: null });
    (context.request.json as Mock).mockRejectedValue(new Error("JSON error"));
    
    const response = await unsubscribePOST(context);
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Server error" });
  });

  it("updates user preferences to disabled with valid token", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-to-unsub", type: "unsubscribe" },
      protectedHeader: { alg: "HS256" },
    });

    // Mock DB response
    const mockEq = vi.fn().mockResolvedValue({ error: null });
    const mockUpdate = vi.fn().mockReturnValue({ eq: mockEq });
    (mockSupabaseAdmin.from as unknown as Mock).mockReturnValue({
      update: mockUpdate,
    });

    const context = createMockContext({
      json: { token: "valid-token" },
      locals: {},
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ success: true });

    expect(mockUpdate).toHaveBeenCalledWith({
      notification_preferences: {
        enabled: false,
        delivery_frequency: "daily",
      },
    });
    expect(mockEq).toHaveBeenCalledWith("id", "user-to-unsub");
  });

  it("rejects if user_id mismatch with token", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "token-user-id", type: "unsubscribe" },
      protectedHeader: { alg: "HS256" },
    });

    const context = createMockContext({
      json: { token: "valid-token", user_id: "different-user-id" },
      locals: {},
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ error: "User ID mismatch" });
  });

  it("returns 500 if database update fails", async () => {
    mockedJwtVerify.mockResolvedValue({
      payload: { sub: "user-123", type: "unsubscribe" },
      protectedHeader: { alg: "HS256" },
    });

    const mockEq = vi
      .fn()
      .mockResolvedValue({ error: { message: "Database error" } });
    const mockUpdate = vi.fn().mockReturnValue({ eq: mockEq });
    (mockSupabaseAdmin.from as unknown as Mock).mockReturnValue({
      update: mockUpdate,
    });

    const context = createMockContext({
      json: { token: "valid-token" },
      locals: {},
    });

    const response = await unsubscribePOST(context);
    expect(response.status).toBe(500);
    expect(await response.json()).toEqual({ error: "Failed to unsubscribe" });
  });
});
