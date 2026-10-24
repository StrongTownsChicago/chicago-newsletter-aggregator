// Client wiring for newsletter cards' "Show more" buttons, which expand a
// summary clamped to two lines.
const CLAMPED_CLASS = "line-clamp-2";

/** Wires every summary toggle on the page to the summary its data-summary-id names. */
export function initSummaryToggles(): void {
  for (const toggle of document.querySelectorAll<HTMLButtonElement>("button[data-summary-id]")) {
    toggle.addEventListener("click", () => {
      const summary = document.getElementById(toggle.dataset.summaryId ?? "");
      if (!summary) return;
      const clamped = summary.classList.toggle(CLAMPED_CLASS);
      toggle.textContent = clamped ? "Show more" : "Show less";
    });
  }
}
