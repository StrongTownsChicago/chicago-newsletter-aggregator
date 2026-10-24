// Shared Observable Plot setup for the /analytics charts (browser only).
// Colors follow the dataviz reference palette: one blue hue for magnitude,
// blue/red around a gray midpoint for above/below average, gray for context.
import * as Plot from "@observablehq/plot";
import { monthTickLabeler } from "../core";
import { EXPORT_SWATCH_ATTRIBUTE, EXPORT_TEXT_ATTRIBUTE } from "./export";

export const CHART_COLORS = {
  series: "#2a78d6",
  seriesLight: "#86b6ef",
  seriesDark: "#1c5cab",
  sequentialLow: "#e6eefa",
  sequentialHigh: "#104281",
  divergingBelow: "#b3322f",
  divergingMidpoint: "#f0efec",
  untracked: "#ebeae6",
  mutedInk: "#52514e",
  baseline: "#c3c2b7",
  surface: "#ffffff",
};

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
export const ROW_HEIGHT = 18;
export const BAR_ROW_HEIGHT = 26;
export const AXIS_BAND = 40;
export const TOP_AXIS_MARGIN = 30;
const LEGEND_MARGIN = 16;
/** Bars fill at most this fraction of their band; the rest is air. */
export const MAX_BAR_THICKNESS = 0.7;
/** Coverage grid columns never get narrower than this; wider grids scroll. */
export const MIN_COVERAGE_CELL_WIDTH = 12;
/** Approximate width of one 12px label character, for sizing label margins. */
const LABEL_CHARACTER_WIDTH = 6.5;
/** Space between a y-axis label and the plot, including the tick. */
const AXIS_TICK_ROOM = 14;

/** A band x axis of consecutive months, labeled to fit the plot's inner width. */
export function monthAxis(months: string[], width: number, marginLeft: number, marginRight: number): Plot.ScaleOptions {
  return {
    type: "band",
    domain: months,
    label: null,
    tickFormat: monthTickLabeler(months, width - marginLeft - marginRight),
  };
}

export function baseOptions(width: number, fontSize = "12px"): Plot.PlotOptions {
  // maxWidth none: wide charts scroll inside their container instead of shrinking illegibly.
  return { width, style: { fontFamily: FONT, fontSize, color: CHART_COLORS.mutedInk, maxWidth: "none" } };
}

/**
 * `Plot.plot`, with each mark layer's label made valid ARIA: Plot names its
 * layers ("cell", "line", ...) with `aria-label` on `<g>` elements that have
 * no role, which ARIA prohibits. Code that selects layers by that label still works.
 */
export function renderPlot(options: Plot.PlotOptions): ReturnType<typeof Plot.plot> {
  const plot = Plot.plot(options);
  plot.querySelectorAll("g[aria-label]:not([role])").forEach((layer) => layer.setAttribute("role", "group"));
  return plot;
}

/** Render the color legend outside the plot so its end labels are never clipped. */
export function withColorLegend(plot: ReturnType<typeof Plot.plot>): HTMLElement {
  const wrapper = document.createElement("div");
  const legend = plot.legend("color", {
    marginLeft: LEGEND_MARGIN,
    marginRight: LEGEND_MARGIN,
    style: { fontFamily: FONT },
  });
  if (legend) wrapper.append(legend);
  wrapper.append(plot);
  return wrapper;
}

interface KeyItem {
  label: string;
  color: string;
  /** Outline color, for swatches that would otherwise vanish on white. */
  outline?: string;
}

/** A legend row of colored swatches (dots or squares) for categories encoded by color. */
export function renderKey(items: KeyItem[], shape: "dot" | "square" = "dot"): HTMLElement {
  const key = document.createElement("div");
  key.className = "flex flex-wrap gap-4 text-xs text-gray-600 mb-2";
  for (const item of items) {
    const entry = document.createElement("span");
    entry.className = "inline-flex items-center gap-1.5";
    const swatch = document.createElement("span");
    swatch.className = `inline-block w-2.5 h-2.5 ${shape === "dot" ? "rounded-full" : "rounded-sm"}`;
    swatch.style.backgroundColor = item.color;
    if (item.outline) swatch.style.boxShadow = `inset 0 0 0 1px ${item.outline}`;
    swatch.setAttribute(EXPORT_SWATCH_ATTRIBUTE, item.outline ?? "");
    const label = document.createElement("span");
    label.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
    label.textContent = item.label;
    entry.append(swatch, label);
    key.append(entry);
  }
  return key;
}

export function wrap(...nodes: Node[]): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.append(...nodes);
  return wrapper;
}

/** Room for the longest y-axis label; narrow screens scroll the chart rather than clip names. */
export function longestLabelMargin(labels: string[]): number {
  return Math.max(...labels.map((label) => label.length), 0) * LABEL_CHARACTER_WIDTH + AXIS_TICK_ROOM;
}
