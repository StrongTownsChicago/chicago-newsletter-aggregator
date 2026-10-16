// Client-side checks for the notification rule form on /preferences.

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
