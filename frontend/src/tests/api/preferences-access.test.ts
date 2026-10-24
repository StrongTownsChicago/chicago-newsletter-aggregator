import { describe, it, expect, vi, beforeEach } from "vitest";

const { admin } = vi.hoisted(() => {
  const eq = vi.fn();
  const single = vi.fn();
  return {
    admin: {
      eq,
      single,
      // Reads record their filter in `eq` too, then resolve through `single`.
      select: vi.fn(() => ({
        eq: vi.fn((...args: unknown[]) => {
          eq(...args);
          return { single };
        }),
      })),
      update: vi.fn(() => ({ eq })),
      from: vi.fn(),
    },
  };
});

vi.mock("../../lib/server/supabase-admin", () => ({
  getSupabaseAdmin: vi.fn(() => ({ from: admin.from })),
}));
vi.mock("jose", () => ({ jwtVerify: vi.fn() }));
vi.mock("../../lib/supabase", () => ({ notificationsEnabled: vi.fn(() => true) }));

import { jwtVerify } from "jose";
import { POST as getUserPreferencesPOST } from "../../pages/api/notifications/get-user-preferences";
import { POST as unsubscribePOST } from "../../pages/api/notifications/unsubscribe";
import { POST as updatePreferencesPOST } from "../../pages/api/notifications/update-preferences";
import { createMockContext, createQueryRecorder, readJsonResponse } from "../helpers";
import { notificationsEnabled } from "../../lib/supabase";

const USER_ID = "user-123";

const verifiedToken = (payload: Record<string, unknown>) =>
  vi.mocked(jwtVerify).mockResolvedValue({
    payload,
    protectedHeader: { alg: "HS256" },
  } as Awaited<ReturnType<typeof jwtVerify>>);

const readPreferences = (json: Record<string, unknown>, locals: Record<string, unknown> = {}) =>
  getUserPreferencesPOST(createMockContext({ json, locals })) as Promise<Response>;

describe("notification preference access", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsEnabled).mockReturnValue(true);
    vi.stubEnv("UNSUBSCRIBE_SECRET_KEY", "test-secret");
    vi.spyOn(console, "error").mockImplementation(() => {});
    admin.from.mockReturnValue({ select: admin.select, update: admin.update });
    admin.single.mockResolvedValue({
      data: { notification_preferences: { enabled: false } },
      error: null,
    });
    admin.eq.mockResolvedValue({ error: null });
  });

  describe("POST /api/notifications/get-user-preferences", () => {
    it.each([
      ["without a user_id", {}],
      ["with their own user_id", { user_id: USER_ID }],
    ])("lets a signed-in user read their own preferences %s", async (_case, json) => {
      const response = await readPreferences(json, { user: { id: USER_ID } });

      expect(response.status).toBe(200);
      expect(await readJsonResponse(response)).toEqual({ enabled: false });
      expect(admin.from).toHaveBeenCalledWith("user_profiles");
      expect(admin.eq).toHaveBeenCalledWith("id", USER_ID);
    });

    it("rejects an unsubscribe token without a subject", async () => {
      verifiedToken({ type: "unsubscribe" });

      const response = await readPreferences({ token: "jwt" });

      expect(response.status).toBe(400);
      expect(admin.from).not.toHaveBeenCalled();
    });

    it("treats preferences that were never set as enabled", async () => {
      admin.single.mockResolvedValue({ data: { notification_preferences: null }, error: null });

      const response = await readPreferences({}, { user: { id: USER_ID } });

      expect(await readJsonResponse(response)).toEqual({ enabled: true });
    });

    it.each([
      ["an error", { data: { notification_preferences: { enabled: true } }, error: { message: "x" } }],
      ["no profile row", { data: null, error: null }],
    ])("returns 404 when the lookup returns %s", async (_case, result) => {
      admin.single.mockResolvedValue(result);

      const response = await readPreferences({}, { user: { id: USER_ID } });

      expect(response.status).toBe(404);
    });
  });

  describe("POST /api/notifications/unsubscribe", () => {
    it("unsubscribes when the submitted user_id matches the token", async () => {
      verifiedToken({ type: "unsubscribe", sub: USER_ID });

      const response = (await unsubscribePOST(
        createMockContext({ json: { token: "jwt", user_id: USER_ID } }),
      ));

      expect(response.status).toBe(200);
      expect(admin.from).toHaveBeenCalledWith("user_profiles");
      expect(admin.eq).toHaveBeenCalledWith("id", USER_ID);
    });
  });

  describe("POST /api/notifications/update-preferences", () => {
    const update = (formData: Record<string, string>, locals: Record<string, unknown>) =>
      updatePreferencesPOST(createMockContext({ formData, locals })) as Promise<Response>;

    it("updates only the signed-in user's profile", async () => {
      const db = createQueryRecorder();

      await update({}, { user: { id: USER_ID }, supabase: db });

      expect(db.update).toHaveBeenCalledWith({
        notification_preferences: { enabled: false, delivery_frequency: "daily" },
      });
      expect(db.eq).toHaveBeenCalledWith("id", USER_ID);
    });

    it("redirects anonymous visitors to login without a query", async () => {
      const db = createQueryRecorder();

      const response = await update({ enabled: "on" }, { user: null, supabase: db });

      expect(response.headers.get("Location")).toBe("/login");
      expect(db.from).not.toHaveBeenCalled();
    });

    it("returns 404 when notifications are disabled", async () => {
      vi.mocked(notificationsEnabled).mockReturnValue(false);
      const db = createQueryRecorder();

      const response = await update({ enabled: "on" }, { user: { id: USER_ID }, supabase: db });

      expect(response.status).toBe(404);
      expect(db.from).not.toHaveBeenCalled();
    });

    it("reports a database failure", async () => {
      const db = createQueryRecorder({ error: { message: "update failed" } });

      const response = await update({}, { user: { id: USER_ID }, supabase: db });
      const location = new URL(response.headers.get("Location")!, "http://localhost");

      expect(location.searchParams.get("error")).toBe("update failed");
    });
  });
});
