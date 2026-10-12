import { describe, expect, it } from "vitest";
import { formatTopicLabel } from "../../lib/topics";

describe("formatTopicLabel", () => {
  it("title-cases underscore-separated slugs", () => {
    expect(formatTopicLabel("bike_lanes")).toBe("Bike Lanes");
    expect(formatTopicLabel("4_flats_legalization")).toBe("4 Flats Legalization");
  });
});
