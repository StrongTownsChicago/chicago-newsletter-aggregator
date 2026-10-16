// The topic definitions: each topic's phrases and how many newsletters mention it.
import {
  describeTopicDefinition,
  describeTopicMatching,
  pluralize,
} from "../../../lib/analytics/descriptions";
import type { DashboardState } from "../dashboard-state";
import { requireElement } from "../dom";

export function renderLensDefinitions(state: DashboardState): void {
  const container = requireElement<HTMLElement>("[data-lens-definitions]");
  const summary = state.data.lenses;
  const rules = document.createElement("p");
  rules.textContent =
    `${describeTopicMatching(summary)} Counts are of ${pluralize(summary.readable_newsletters, "newsletter")}, all dates. ` +
    "Strong Towns Chicago focus topics overlap the broader ones.";
  const list = document.createElement("dl");
  list.className = "space-y-2";
  for (const lens of summary.lenses) {
    const { title, body } = describeTopicDefinition(lens, summary.readable_newsletters);
    const term = document.createElement("dt");
    term.className = "font-semibold text-gray-900";
    term.textContent = title;
    const definition = document.createElement("dd");
    definition.textContent = body;
    list.append(term, definition);
  }
  container.replaceChildren(rules, list);
}
