import { describe, expect, it } from "vitest";
import { areNotificationsEnabled } from "../../lib/notification-preferences";

describe("areNotificationsEnabled", () => {
  it("is off only when the preferences say enabled: false", () => {
    expect(areNotificationsEnabled({ enabled: false, delivery_frequency: "daily" })).toBe(false);
    expect(areNotificationsEnabled({ enabled: true, delivery_frequency: "daily" })).toBe(true);
  });

  it("treats missing or malformed preferences as on, like the column default", () => {
    expect(areNotificationsEnabled(null)).toBe(true);
    expect(areNotificationsEnabled(undefined)).toBe(true);
    expect(areNotificationsEnabled({})).toBe(true);
    expect(areNotificationsEnabled([false])).toBe(true);
    expect(areNotificationsEnabled("off")).toBe(true);
  });
});
