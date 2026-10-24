import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../lib/supabase", () => ({
  notificationsEnabled: vi.fn(() => true),
}));

import { POST as createRulePOST } from "../../pages/api/notifications/create-rule";
import { createMockContext, createQueryRecorder } from "../helpers";

const USER_ID = "user-123";

const submit = (
  db: ReturnType<typeof createQueryRecorder>,
  formData: Record<string, string | string[]>,
) =>
  createRulePOST(
    createMockContext({ locals: { user: { id: USER_ID }, supabase: db }, formData }),
  ) as Promise<Response>;

const errorOf = (response: Response) =>
  new URL(response.headers.get("Location")!, "http://localhost").searchParams.get("error");

describe("POST /api/notifications/create-rule", () => {
  let db: ReturnType<typeof createQueryRecorder>;

  beforeEach(() => {
    vi.clearAllMocks();
    db = createQueryRecorder({ count: 0, error: null }, { error: null });
  });

  it("counts only the signed-in user's rules toward the limit", async () => {
    await submit(db, { name: "Rule", topics: ["transit"] });

    expect(db.select).toHaveBeenCalledWith("*", { count: "exact", head: true });
    expect(db.eq).toHaveBeenCalledWith("user_id", USER_ID);
  });

  it("allows a fifth rule", async () => {
    db = createQueryRecorder({ count: 4, error: null });

    await submit(db, { name: "Rule", topics: ["transit"] });

    expect(db.insert).toHaveBeenCalled();
  });

  it("trims the search phrase and ward numbers and drops blank wards", async () => {
    await submit(db, { name: "Rule", search_term: "  bike lanes  ", wards: [" 5 ", "", "  "] });

    expect(db.insert).toHaveBeenCalledWith(
      expect.objectContaining({ search_term: "bike lanes", ward_numbers: ["5"] }),
    );
  });

  it("stores no ward filter, an inactive rule and daily delivery by default", async () => {
    await submit(db, { name: "Rule", topics: ["transit"] });

    expect(db.insert).toHaveBeenCalledWith(
      expect.objectContaining({
        user_id: USER_ID,
        ward_numbers: null,
        is_active: false,
        delivery_frequency: "daily",
      }),
    );
  });

  it("stores an unknown delivery frequency as daily", async () => {
    await submit(db, { name: "Rule", topics: ["transit"], delivery_frequency: "hourly" });

    expect(db.insert).toHaveBeenCalledWith(
      expect.objectContaining({ delivery_frequency: "daily" }),
    );
  });

  it("rejects ward filters on weekly rules before any query", async () => {
    const response = await submit(db, {
      name: "Rule",
      topics: ["transit"],
      wards: ["5"],
      delivery_frequency: "weekly",
    });

    expect(errorOf(response)).toContain("Ward filters cannot be applied to weekly summaries");
    expect(db.from).not.toHaveBeenCalled();
  });

  it("stores weekly rules without a ward filter", async () => {
    await submit(db, { name: "Rule", topics: ["transit"], delivery_frequency: "weekly" });

    expect(db.insert).toHaveBeenCalledWith(expect.objectContaining({ ward_numbers: null }));
  });

  it("accepts a 100-character search phrase and rejects 101", async () => {
    await submit(db, { name: "Rule", search_term: "a".repeat(100) });
    expect(db.insert).toHaveBeenCalled();

    const tooLong = createQueryRecorder();
    const response = await submit(tooLong, { name: "Rule", search_term: "a".repeat(101) });

    expect(errorOf(response)).toBe("Search phrase must be under 100 characters");
    expect(tooLong.from).not.toHaveBeenCalled();
  });

  it("does not insert when the rule count fails", async () => {
    db = createQueryRecorder({ count: null, error: { message: "count failed" } });

    const response = await submit(db, { name: "Rule", topics: ["transit"] });

    expect(errorOf(response)).toBe("count failed");
    expect(db.insert).not.toHaveBeenCalled();
  });

  it("reports an insert failure", async () => {
    db = createQueryRecorder({ count: 0, error: null }, { error: { message: "insert failed" } });

    const response = await submit(db, { name: "Rule", topics: ["transit"] });

    expect(errorOf(response)).toBe("insert failed");
  });
});
