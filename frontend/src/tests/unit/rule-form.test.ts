import { describe, expect, it } from "vitest";
import { findRuleFormError, ruleEditAttributes } from "../../lib/rule-form";
import type { NotificationRule } from "../../lib/supabase";

describe("findRuleFormError", () => {
  it("requires a topic for weekly rules, even with a search phrase", () => {
    expect(findRuleFormError({ frequency: "weekly", searchTerm: "zoning", topicCount: 0 })).toBe(
      "Please select at least one topic for weekly summaries.",
    );
    expect(findRuleFormError({ frequency: "weekly", searchTerm: "", topicCount: 1 })).toBeNull();
  });

  it("requires a topic or a search phrase for daily rules", () => {
    expect(findRuleFormError({ frequency: "daily", searchTerm: "", topicCount: 0 })).toBe(
      "Please select at least one topic or enter a search phrase for daily digest.",
    );
    expect(findRuleFormError({ frequency: "daily", searchTerm: "zoning", topicCount: 0 })).toBeNull();
    expect(findRuleFormError({ frequency: "daily", searchTerm: "", topicCount: 2 })).toBeNull();
  });

  it("treats an unknown frequency as daily", () => {
    expect(findRuleFormError({ frequency: "", searchTerm: "", topicCount: 0 })).toMatch(/daily digest/);
  });
});

describe("ruleEditAttributes", () => {
  const rule: NotificationRule = {
    id: "r1",
    user_id: "u1",
    name: "Bikes",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    topics: ["transportation"],
    search_term: "bike lanes",
    ward_numbers: ["2", "40"],
    delivery_frequency: "weekly",
    min_relevance_score: null,
    source_ids: null,
  };

  it("describes a saved rule for its edit button", () => {
    expect(ruleEditAttributes(rule)).toEqual({
      "data-rule-id": "r1",
      "data-rule-name": "Bikes",
      "data-rule-topics": '["transportation"]',
      "data-rule-ward-numbers": '["2","40"]',
      "data-rule-search-term": "bike lanes",
      "data-rule-delivery-frequency": "weekly",
    });
  });

  it("fills in missing wards, phrase and frequency", () => {
    const sparse = { ...rule, search_term: undefined, ward_numbers: undefined, delivery_frequency: "" } as unknown as NotificationRule;
    expect(ruleEditAttributes(sparse)).toMatchObject({
      "data-rule-ward-numbers": "[]",
      "data-rule-search-term": "",
      "data-rule-delivery-frequency": "daily",
    });
  });
});
