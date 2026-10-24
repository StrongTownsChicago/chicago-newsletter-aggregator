import { describe, expect, it } from "vitest";
import * as Plot from "@observablehq/plot";
import { renderPlot } from "../../lib/analytics/charts/common";

const rows = [
  { month: "2026-01", wards: 3 },
  { month: "2026-02", wards: 5 },
];

describe("renderPlot", () => {
  it("gives every labelled mark layer a group role and keeps the labels", () => {
    const plot = renderPlot({ marks: [Plot.barY(rows, { x: "month", y: "wards" }), Plot.ruleY([0])] });

    const labelledLayers = [...plot.querySelectorAll("g[aria-label]")];
    expect(labelledLayers.length).toBeGreaterThan(0);
    expect(labelledLayers.map((layer) => layer.getAttribute("role"))).toEqual(labelledLayers.map(() => "group"));
    expect(plot.querySelector('g[aria-label="bar"]')).not.toBeNull();
  });
});
