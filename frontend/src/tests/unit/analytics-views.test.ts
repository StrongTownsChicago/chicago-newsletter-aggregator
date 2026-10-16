import { describe, expect, it } from "vitest";
import {
  clearViewSelection,
  DASHBOARD_PANEL_IDS,
  describeDashboardView,
  focusedWard,
  selectDashboardView,
  VIEW_PANELS,
} from "../../lib/analytics-views";

const labels = { ward: (ward: string) => `Ward ${ward}`, topic: (id: string) => id.toUpperCase() };

describe("selectDashboardView", () => {
  it("shows the overview with no ward or topic, or with several wards", () => {
    expect(selectDashboardView({ wards: [], lens: null })).toBe("overview");
    expect(selectDashboardView({ wards: ["1", "2"], lens: null })).toBe("overview");
  });

  it("shows the topic view for a topic without a single ward", () => {
    expect(selectDashboardView({ wards: [], lens: "parks" })).toBe("topic");
    expect(selectDashboardView({ wards: ["1", "2"], lens: "parks" })).toBe("topic");
  });

  it("shows the ward view for one ward, with or without a topic", () => {
    expect(selectDashboardView({ wards: ["5"], lens: null })).toBe("ward");
    expect(selectDashboardView({ wards: ["5"], lens: "parks" })).toBe("ward");
  });
});

describe("focusedWard", () => {
  it("is the only selected ward", () => {
    expect(focusedWard({ wards: ["5"] })).toBe("5");
    expect(focusedWard({ wards: [] })).toBeNull();
    expect(focusedWard({ wards: ["5", "6"] })).toBeNull();
  });
});

describe("VIEW_PANELS", () => {
  it("lists only known panels, each once", () => {
    for (const panels of Object.values(VIEW_PANELS)) {
      expect(new Set(panels).size).toBe(panels.length);
      for (const id of panels) expect(DASHBOARD_PANEL_IDS).toContain(id);
    }
  });

  it("puts the selection's panel first and drops city-wide panels from the ward view", () => {
    expect(VIEW_PANELS.topic.slice(0, 2)).toEqual(["topic-detail", "civic-calendar"]);
    expect(VIEW_PANELS.ward[0]).toBe("ward-profile");
    expect(VIEW_PANELS.ward).toContain("term-explorer");
    for (const id of ["civic-calendar", "rising-terms", "sending-cadence", "topic-detail"] as const) {
      expect(VIEW_PANELS.ward).not.toContain(id);
    }
    expect(VIEW_PANELS.overview).not.toContain("topic-detail");
    expect(VIEW_PANELS.overview).not.toContain("ward-profile");
  });
});

describe("clearViewSelection", () => {
  it("drops wards and topic but keeps the dates", () => {
    expect(clearViewSelection({ wards: ["5"], lens: "parks", fromMonth: "2026-01", toMonth: "2026-03" })).toEqual({
      wards: [],
      lens: null,
      fromMonth: "2026-01",
      toMonth: "2026-03",
    });
  });
});

describe("describeDashboardView", () => {
  it("names the selection", () => {
    expect(describeDashboardView({ wards: [], lens: null }, labels)).toBe("Overview");
    expect(describeDashboardView({ wards: ["1", "2"], lens: "parks" }, labels)).toBe("PARKS");
    expect(describeDashboardView({ wards: ["5"], lens: null }, labels)).toBe("Ward 5");
    expect(describeDashboardView({ wards: ["5"], lens: "parks" }, labels)).toBe("Ward 5 · PARKS");
  });
});
