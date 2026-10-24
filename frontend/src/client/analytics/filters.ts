// The /analytics filter bar: reading it, filling its options, and describing its date window.
import {
  classifyDateWindow,
  formatMonth,
  listWindowMonths,
  type AnalyticsFilters,
  type LensDefinition,
} from "../../lib/analytics/core";
import { describeBroadCoverageRule, describeMonthSpan, pluralize } from "../../lib/analytics/descriptions";
import { formatWard } from "../../lib/analytics/format";
import type { DashboardState } from "./dashboard-state";
import { requireElement } from "./dom";

export function readFilters(form: HTMLFormElement): AnalyticsFilters {
  const formData = new FormData(form);
  const wards = [...form.querySelectorAll<HTMLInputElement>('input[name="ward"]:checked')].map(
    (input) => input.value,
  );
  return {
    wards,
    lens: (formData.get("lens") as string) || null,
    fromMonth: (formData.get("from") as string) || null,
    toMonth: (formData.get("to") as string) || null,
  };
}

/** The choices the filter bar offers. */
export interface FilterOptions {
  wards: string[];
  months: string[];
  lenses: LensDefinition[];
}

export function populateFilterOptions(
  form: HTMLFormElement,
  { wards, months, lenses }: FilterOptions,
  defaultFromMonth: string | null,
): void {
  requireElement<HTMLSelectElement>('select[name="lens"]', form).append(
    ...lenses.map((lens) => new Option(lens.label, lens.id)),
  );
  const wardOptions = requireElement<HTMLElement>("#ward-options");
  wardOptions.replaceChildren(
    ...wards.map((ward) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-1 text-sm text-gray-700 px-1 py-0.5 rounded hover:bg-gray-50";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "ward";
      input.value = ward;
      input.setAttribute("aria-label", formatWard(ward));
      label.append(input, ward);
      return label;
    }),
  );
  for (const name of ["from", "to"]) {
    const select = requireElement<HTMLSelectElement>(`select[name="${name}"]`, form);
    select.append(...months.map((month) => new Option(formatMonth(month), month)));
  }
  // Start on the broad-coverage window. defaultSelected makes "Reset filters" return to it.
  const defaultOption = [...requireElement<HTMLSelectElement>('select[name="from"]', form).options].find(
    (option) => option.value === defaultFromMonth,
  );
  if (defaultOption) {
    defaultOption.defaultSelected = true;
    defaultOption.selected = true;
  }
}

/** Open-ended date window starting at fromMonth (null = the start of the archive). */
export function setDateWindow(form: HTMLFormElement, fromMonth: string | null): void {
  requireElement<HTMLSelectElement>('select[name="from"]', form).value = fromMonth ?? "";
  requireElement<HTMLSelectElement>('select[name="to"]', form).value = "";
}

export function updateWardSummary(filters: AnalyticsFilters): void {
  const summary = requireElement<HTMLElement>("#ward-summary");
  summary.textContent =
    filters.wards.length === 0
      ? "All wards"
      : filters.wards.length <= 3
        ? filters.wards.map(formatWard).join(", ")
        : `${filters.wards.length} wards`;
}

export function renderDateWindowStatus(state: DashboardState, filters: AnalyticsFilters): void {
  const status = requireElement<HTMLElement>("#date-window-status");
  const toggle = requireElement<HTMLButtonElement>("#date-window-toggle");
  const broadWindow = state.broadWindow;
  const kind = classifyDateWindow(filters, broadWindow);
  const span = describeMonthSpan(listWindowMonths(filters, state.dataMonths));
  toggle.hidden = !broadWindow;
  toggle.textContent = kind === "full" ? "Show default dates" : "Show all dates";
  if (broadWindow && kind === "broad") {
    status.textContent = `${span}: months when ${describeBroadCoverageRule(broadWindow)}.`;
  } else if (broadWindow && kind === "full") {
    status.textContent =
      `${span}. Before ${formatMonth(broadWindow.startMonth)}, at most ` +
      `${pluralize(broadWindow.maxActiveWardsBefore, "ward")} a month sent newsletters.`;
  } else {
    status.textContent = `${span}.`;
  }
}

export function setWardSelection(form: HTMLFormElement, wards: string[]): void {
  form.querySelectorAll<HTMLInputElement>('input[name="ward"]').forEach((input) => {
    input.checked = wards.includes(input.value);
  });
}

/** How long the mouse can be outside the ward picker before it closes, so crossing the gap to its panel doesn't. */
const WARD_PICKER_LEAVE_DELAY_MS = 300;

/**
 * Close the ward picker when the mouse leaves it, a click or focus lands outside it, or Escape is pressed.
 * Mouse-leave ignores touch and pen, which have no hover.
 */
export function wireWardPickerDismissal(picker: HTMLDetailsElement): void {
  let leaveTimer: ReturnType<typeof setTimeout> | undefined;
  const close = () => {
    clearTimeout(leaveTimer);
    picker.open = false;
  };
  picker.addEventListener("pointerleave", (event) => {
    if (picker.open && event.pointerType === "mouse") leaveTimer = setTimeout(close, WARD_PICKER_LEAVE_DELAY_MS);
  });
  picker.addEventListener("pointerenter", () => clearTimeout(leaveTimer));
  const closeIfOutside = (event: Event) => {
    if (picker.open && !picker.contains(event.target as Node)) close();
  };
  document.addEventListener("pointerdown", closeIfOutside);
  document.addEventListener("focusin", closeIfOutside);
  picker.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !picker.open) return;
    close();
    requireElement<HTMLElement>("summary", picker).focus();
  });
}
