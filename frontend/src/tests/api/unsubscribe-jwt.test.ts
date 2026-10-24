import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SignJWT, UnsecuredJWT } from "jose";
import type { APIRoute } from "astro";
import { POST as validateTokenPOST } from "../../pages/api/notifications/validate-unsubscribe-token";
import { POST as getUserPreferencesPOST } from "../../pages/api/notifications/get-user-preferences";
import { POST as unsubscribePOST } from "../../pages/api/notifications/unsubscribe";
import { createMockContext } from "../helpers";

// Real jose verification (unsubscribe.test.ts mocks it): the routes must reject
// expired tokens, other keys and other algorithms, not just bad payloads.

const { mockSupabaseAdmin } = vi.hoisted(() => {
  const eq = vi.fn();
  return {
    mockSupabaseAdmin: {
      eq,
      from: vi.fn(() => ({
        update: vi.fn(() => ({ eq })),
        select: vi.fn(() => ({ eq: vi.fn(() => ({ single: eq })) })),
      })),
    },
  };
});

vi.mock("../../lib/server/supabase-admin", () => ({
  getSupabaseAdmin: vi.fn(() => mockSupabaseAdmin),
}));

const SECRET = "test-secret-key-for-testing-must-be-at-least-32-chars-long";
const encode = (secret: string) => new TextEncoder().encode(secret);

const signToken = ({
  secret = SECRET,
  alg = "HS256",
  type = "unsubscribe",
  expiresAt = "1h",
}: { secret?: string; alg?: string; type?: string; expiresAt?: string | number } = {}) =>
  new SignJWT({ type })
    .setProtectedHeader({ alg })
    .setSubject("user-123")
    .setIssuedAt()
    .setExpirationTime(expiresAt)
    .sign(encode(secret));

const routes: [string, APIRoute][] = [
  ["validate-unsubscribe-token", validateTokenPOST],
  ["get-user-preferences", getUserPreferencesPOST],
  ["unsubscribe", unsubscribePOST],
];

const post = (route: APIRoute, token: string) =>
  route(createMockContext({ json: { token }, locals: {} })) as Promise<Response>;

describe("unsubscribe token verification", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubEnv("UNSUBSCRIBE_SECRET_KEY", SECRET);
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockSupabaseAdmin.eq.mockResolvedValue({
      data: { notification_preferences: { enabled: true } },
      error: null,
    });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  describe.each(routes)("%s", (_name, route) => {
    it("accepts a current HS256 token signed with the secret", async () => {
      const response = await post(route, await signToken());

      expect(response.status).toBe(200);
    });

    it("rejects an expired token", async () => {
      const expiredAt = Math.floor(Date.now() / 1000) - 60;
      const response = await post(route, await signToken({ expiresAt: expiredAt }));

      expect(response.status).toBe(400);
      expect(mockSupabaseAdmin.from).not.toHaveBeenCalled();
    });

    it("rejects a token signed with another key", async () => {
      const response = await post(route, await signToken({ secret: `${SECRET}-other` }));

      expect(response.status).toBe(400);
      expect(mockSupabaseAdmin.from).not.toHaveBeenCalled();
    });

    it("rejects a token signed with an algorithm other than HS256", async () => {
      const response = await post(route, await signToken({ alg: "HS512" }));

      expect(response.status).toBe(400);
      expect(mockSupabaseAdmin.from).not.toHaveBeenCalled();
    });

    it("rejects an unsigned token", async () => {
      const unsigned = new UnsecuredJWT({ type: "unsubscribe" })
        .setSubject("user-123")
        .setExpirationTime("1h")
        .encode();

      const response = await post(route, unsigned);

      expect(response.status).toBe(400);
      expect(mockSupabaseAdmin.from).not.toHaveBeenCalled();
    });

    it("rejects a valid token of another type", async () => {
      const response = await post(route, await signToken({ type: "access" }));

      expect(response.status).toBe(400);
      expect(mockSupabaseAdmin.from).not.toHaveBeenCalled();
    });
  });
});
