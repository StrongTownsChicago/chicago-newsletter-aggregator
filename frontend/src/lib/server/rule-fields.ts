// Server-side reading and validation of the notification rule form, shared by the
// create-rule and update-rule routes. Client-side checks live in lib/rule-form.ts.
import { formText, formTexts } from "./form-data";

const MAX_SEARCH_TERM_LENGTH = 100;

/** The notification_rules columns a submitted rule form sets. */
export interface RuleFields {
  topics: string[];
  search_term: string | null;
  ward_numbers: string[] | null;
  is_active: boolean;
  delivery_frequency: "daily" | "weekly";
}

export type RuleFieldsResult = { fields: RuleFields; error?: never } | { error: string; fields?: never };

/** The submitted form's values, trimmed, before any rule-type checks. */
interface SubmittedRule {
  topics: string[];
  searchTerm: string | null;
  wards: string[];
  isActive: boolean;
}

function readWeeklyRuleFields({ topics, wards, isActive }: SubmittedRule): RuleFieldsResult {
  if (topics.length === 0) {
    return { error: "At least one topic is required for weekly summaries" };
  }
  if (wards.length > 0) {
    return {
      error:
        "Ward filters cannot be applied to weekly summaries. Weekly summaries cover citywide activity.",
    };
  }
  return {
    fields: { topics, search_term: null, ward_numbers: null, is_active: isActive, delivery_frequency: "weekly" },
  };
}

function readDailyRuleFields({ topics, searchTerm, wards, isActive }: SubmittedRule): RuleFieldsResult {
  if (!searchTerm && topics.length === 0) {
    return { error: "Please specify at least one topic or search phrase" };
  }
  if (searchTerm && searchTerm.length > MAX_SEARCH_TERM_LENGTH) {
    return { error: `Search phrase must be under ${MAX_SEARCH_TERM_LENGTH} characters` };
  }
  return {
    fields: {
      topics,
      search_term: searchTerm,
      ward_numbers: wards.length > 0 ? wards : null,
      is_active: isActive,
      delivery_frequency: "daily",
    },
  };
}

/**
 * The rule's fields, or why they can't be saved. Weekly rules need a topic and take no
 * wards or search phrase; anything not weekly is daily and needs a topic or a phrase.
 */
export function readRuleFields(formData: FormData): RuleFieldsResult {
  const submitted: SubmittedRule = {
    topics: formTexts(formData, "topics"),
    searchTerm: formText(formData, "search_term")?.trim() || null,
    wards: formTexts(formData, "wards")
      .map((ward) => ward.trim())
      .filter((ward) => ward.length > 0),
    isActive: formData.get("is_active") === "on",
  };
  return formText(formData, "delivery_frequency") === "weekly"
    ? readWeeklyRuleFields(submitted)
    : readDailyRuleFields(submitted);
}
