// Topics users can subscribe to, grouped by category for display.
// Must stay in sync with backend/processing/llm_processor.py:TOPICS.
export const TOPIC_CATEGORIES: Record<string, string[]> = {
  "Incremental Housing": [
    "4_flats_legalization",
    "missing_middle_housing",
    "accessory_dwelling_units",
    "single_stair_reform",
  ],
  Streets: ["bike_lanes", "street_redesign", "street_safety_or_traffic_calming"],
  Transit: ["transit_funding"],
  Transparency: ["city_budget", "tax_policy"],
  Governance: ["zoning_or_development_meeting_or_approval", "city_charter"],
};

export const ALL_TOPICS: string[] = Object.values(TOPIC_CATEGORIES).flat();

/** Display labels for topic IDs. IDs stay unchanged in URLs and stored data. */
export const TOPIC_LABELS: Readonly<Record<string, string>> = {
  "4_flats_legalization": "4-flats legalization",
  missing_middle_housing: "Missing middle housing",
  accessory_dwelling_units: "Accessory dwelling units (ADUs)",
  single_stair_reform: "Single-stair reform",
  bike_lanes: "Bike lanes",
  street_redesign: "Street redesign",
  street_safety_or_traffic_calming: "Street safety & traffic calming",
  transit_funding: "Transit funding",
  city_budget: "City budget",
  tax_policy: "Tax policy",
  zoning_or_development_meeting_or_approval: "Zoning & development approvals",
  city_charter: "City charter",
};

/**
 * Readable label for a topic ID. Unknown IDs (e.g. retired topics still on old
 * newsletters) get underscores replaced with spaces and a capital first letter.
 */
export function formatTopicLabel(topicId: string): string {
  if (Object.hasOwn(TOPIC_LABELS, topicId)) {
    return TOPIC_LABELS[topicId];
  }
  const spaced = topicId.split("_").filter(Boolean).join(" ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
