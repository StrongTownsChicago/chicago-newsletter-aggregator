import { describe, expect, it } from "vitest";
import { findRuleFormError } from "../../lib/rule-form";

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
