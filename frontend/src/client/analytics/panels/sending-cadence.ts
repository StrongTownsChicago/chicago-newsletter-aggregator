// Sending cadence panel: the longest gaps between a source's newsletters.
import type { NewsletterFact } from "../../../lib/analytics/core";
import { findLongestGaps } from "../../../lib/analytics/coverage";
import { pluralize } from "../../../lib/analytics/descriptions";
import { sourceLabel } from "../../../lib/analytics/format";
import { panel, requireElement, setTable } from "../dom";

const GAP_LIMIT = 10;

export function renderCadencePanel(facts: NewsletterFact[]): void {
  const { section, caption } = panel("sending-cadence");
  caption.textContent = `From ${pluralize(facts.length, "newsletter")}.`;
  setTable(
    requireElement<HTMLElement>("#cadence-gaps", section),
    [
      { label: "Source", value: (gap) => sourceLabel({ name: gap.alder ?? `Source ${gap.sourceId}`, ward: gap.ward }) },
      { label: "From", value: (gap) => gap.from },
      { label: "To", value: (gap) => gap.to },
      { label: "Days", value: (gap) => gap.days, numeric: true },
    ],
    findLongestGaps(facts, GAP_LIMIT),
  );
}
