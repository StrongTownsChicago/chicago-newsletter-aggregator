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
