// The notification rule form on /preferences: client-side checks, and the
// data attributes an edit button carries to fill the form with a saved rule.
import type { NotificationRule } from "./supabase";

export interface RuleFormInput {
  /** "weekly" or "daily"; anything else is treated as daily. */
  frequency: string;
  /** The search phrase, already trimmed. */
  searchTerm: string;
  /** How many topics are checked. */
  topicCount: number;
}

/**
 * Why the rule can't be saved, or null when it can. Weekly rules need a topic;
 * daily rules need a topic or a search phrase.
 */
export function findRuleFormError({ frequency, searchTerm, topicCount }: RuleFormInput): string | null {
  const hasTopics = topicCount > 0;
  if (frequency === "weekly") {
    return hasTopics ? null : "Please select at least one topic for weekly summaries.";
  }
  return hasTopics || searchTerm
    ? null
    : "Please select at least one topic or enter a search phrase for daily digest.";
}

/** A saved rule's edit-button data attributes, read back by client/rule-modal.ts. */
export function ruleEditAttributes(rule: NotificationRule): Record<string, string> {
  return {
    "data-rule-id": rule.id,
    "data-rule-name": rule.name,
    "data-rule-topics": JSON.stringify(rule.topics),
    "data-rule-ward-numbers": JSON.stringify(rule.ward_numbers || []),
    "data-rule-search-term": rule.search_term || "",
    "data-rule-delivery-frequency": rule.delivery_frequency || "daily",
  };
}
