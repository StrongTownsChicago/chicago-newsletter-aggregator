// Text formats shared by the /analytics charts, tables and summary tiles.
import type { SourceCoverage } from "./analytics";
import type { CoverageStatus } from "./analytics-coverage";
import type { LensReachCell, LensWardStatus } from "./analytics-reach";

const countFormat = new Intl.NumberFormat("en-US");
const medianFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** "1,234". */
export function formatCount(value: number): string {
  return countFormat.format(value);
}

/** A median to one decimal place, or "–" when there is none. */
export function formatMedian(value: number | null): string {
  return value === null ? "–" : medianFormat.format(value);
}

export const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;
export const formatWard = (ward: string): string => `Ward ${ward}`;
export const formatOptionalShare = (share: number | null): string =>
  share === null ? "too few newsletters that month for a share" : formatPercent(share);
/** Lifts against near-zero baselines are unstable; above this, just say "over". */
const MAX_DISPLAYED_LIFT = 100;
export const formatLift = (lift: number): string =>
  lift > MAX_DISPLAYED_LIFT ? `>${MAX_DISPLAYED_LIFT}×` : `${lift.toFixed(1)}×`;

export function sourceLabel(source: Pick<SourceCoverage, "name" | "ward">): string {
  return source.ward ? `${source.name} (Ward ${source.ward})` : source.name;
}

/** "14 of 38 wards (37%)": a ward-reach cell with its denominator. */
export function describeWardReach(cell: LensReachCell): string {
  return cell.share === null
    ? "no ward sent newsletters"
    : `${cell.wardsMentioning} of ${cell.activeWards} wards (${formatPercent(cell.share)})`;
}

export const LENS_WARD_STATUS_LABELS: Record<LensWardStatus, string> = {
  mentioned: "Mentioned it",
  not_mentioned: "Didn't mention it",
  no_newsletter: "No newsletter",
};

export const COVERAGE_STATUS_LABELS: Record<CoverageStatus, string> = {
  untracked: "Not tracked yet",
  silent: "None received",
  received: "Received",
};
