import { describe, it, expect, vi, beforeEach } from "vitest";
import type { APIRoute } from "astro";

vi.mock("../../lib/supabase", () => ({
  notificationsEnabled: vi.fn(() => true),
}));

import { POST as updateRulePOST } from "../../pages/api/notifications/update-rule";
import { POST as deleteRulePOST } from "../../pages/api/notifications/delete-rule";
import { createMockContext, createQueryRecorder } from "../helpers";
import { notificationsEnabled } from "../../lib/supabase";

const USER_ID = "user-123";
const RULE_ID = "rule-456";

const submit = (
  route: APIRoute,
  db: ReturnType<typeof createQueryRecorder>,
  formData: Record<string, string | string[]>,
) =>
  route(
    createMockContext({ locals: { user: { id: USER_ID }, supabase: db }, formData }),
  ) as Promise<Response>;

const redirectParams = (response: Response) =>
  new URL(response.headers.get("Location")!, "http://localhost").searchParams;

const routes: [string, APIRoute][] = [
  ["update-rule", updateRulePOST],
  ["delete-rule", deleteRulePOST],
];

const ruleForm = { rule_id: RULE_ID, name: "Rule", topics: ["transit"] };

describe("rule update and delete", () => {
  let db: ReturnType<typeof createQueryRecorder>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsEnabled).mockReturnValue(true);
    db = createQueryRecorder();
  });

  describe.each(routes)("%s", (_name, route) => {
    it("scopes the change to the rule and its owner", async () => {
      await submit(route, db, ruleForm);

      expect(db.from).toHaveBeenCalledWith("notification_rules");
      expect(db.eq).toHaveBeenCalledWith("id", RULE_ID);
      expect(db.eq).toHaveBeenCalledWith("user_id", USER_ID);
    });

    it("redirects anonymous visitors to login without a query", async () => {
      const response = (await route(
        createMockContext({ locals: { user: null, supabase: db }, formData: ruleForm }),
      ));

      expect(response.headers.get("Location")).toBe("/login");
      expect(db.from).not.toHaveBeenCalled();
    });

    it("returns 404 when notifications are disabled", async () => {
      vi.mocked(notificationsEnabled).mockReturnValue(false);

      const response = await submit(route, db, ruleForm);

      expect(response.status).toBe(404);
      expect(db.from).not.toHaveBeenCalled();
    });

    it("reports a database failure", async () => {
      db = createQueryRecorder({ error: { message: "write failed" } });

      const response = await submit(route, db, ruleForm);

      expect(redirectParams(response).get("error")).toBe("write failed");
      expect(redirectParams(response).has("message")).toBe(false);
    });
  });

  describe("POST /api/notifications/update-rule", () => {
    it("defaults to daily delivery, inactive and no ward filter", async () => {
      await submit(updateRulePOST, db, ruleForm);

      expect(db.update).toHaveBeenCalledWith(
        expect.objectContaining({
          delivery_frequency: "daily",
          is_active: false,
          search_term: null,
          ward_numbers: null,
        }),
      );
    });

    it("trims the search phrase and ward numbers and keeps the active flag", async () => {
      await submit(updateRulePOST, db, {
        ...ruleForm,
        search_term: "  bike lanes  ",
        wards: [" 5 ", "", "  "],
        is_active: "on",
      });

      expect(db.update).toHaveBeenCalledWith(
        expect.objectContaining({ search_term: "bike lanes", ward_numbers: ["5"], is_active: true }),
      );
    });

    it("clears the search phrase on weekly rules", async () => {
      await submit(updateRulePOST, db, {
        ...ruleForm,
        search_term: "bike lanes",
        delivery_frequency: "weekly",
      });

      expect(db.update).toHaveBeenCalledWith(
        expect.objectContaining({
          search_term: null,
          ward_numbers: null,
          delivery_frequency: "weekly",
        }),
      );
    });

    it.each([
      [
        "a weekly rule without topics",
        { rule_id: RULE_ID, name: "Rule", search_term: "x", delivery_frequency: "weekly" },
        "At least one topic is required for weekly summaries",
      ],
      [
        "a weekly rule with ward filters",
        { ...ruleForm, wards: ["5"], delivery_frequency: "weekly" },
        "Ward filters cannot be applied to weekly summaries. Weekly summaries cover citywide activity.",
      ],
      [
        "a daily rule without topics or a search phrase",
        { rule_id: RULE_ID, name: "Rule", search_term: "   " },
        "Please specify at least one topic or search phrase",
      ],
      [
        "a search phrase over 100 characters",
        { ...ruleForm, search_term: "a".repeat(101) },
        "Search phrase must be under 100 characters",
      ],
      [
        "a missing name",
        { rule_id: RULE_ID, topics: ["transit"] },
        "Rule ID and name are required",
      ],
    ])("rejects %s before any query", async (_case, formData, error) => {
      const response = await submit(updateRulePOST, db, formData);

      expect(redirectParams(response).get("error")).toBe(error);
      expect(db.from).not.toHaveBeenCalled();
    });

    it("accepts a 100-character search phrase", async () => {
      await submit(updateRulePOST, db, { ...ruleForm, search_term: "a".repeat(100) });

      expect(db.update).toHaveBeenCalled();
    });

    it("stores any frequency other than weekly as daily, as create-rule does", async () => {
      await submit(updateRulePOST, db, { ...ruleForm, delivery_frequency: "hourly" });

      expect(db.update).toHaveBeenCalledWith(
        expect.objectContaining({ delivery_frequency: "daily" }),
      );
    });
  });
});
