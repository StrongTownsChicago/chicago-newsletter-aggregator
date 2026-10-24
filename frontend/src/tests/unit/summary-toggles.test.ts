import { beforeEach, describe, expect, it } from "vitest";
import { initSummaryToggles } from "../../client/summary-toggles";

const summary = (id: string) => document.getElementById(id)!;
const toggle = (id: string) => document.querySelector<HTMLButtonElement>(`[data-summary-id="${id}"]`)!;

describe("initSummaryToggles", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <p id="summary-a" class="text-gray-700 line-clamp-2">A</p>
      <button type="button" data-summary-id="summary-a">Show more</button>
      <p id="summary-b" class="text-gray-700 line-clamp-2">B</p>
      <button type="button" data-summary-id="summary-b">Show more</button>`;
    initSummaryToggles();
  });

  it("expands only its own summary, then clamps it again", () => {
    toggle("summary-a").click();
    expect(summary("summary-a").classList.contains("line-clamp-2")).toBe(false);
    expect(toggle("summary-a").textContent).toBe("Show less");
    expect(summary("summary-b").classList.contains("line-clamp-2")).toBe(true);

    toggle("summary-a").click();
    expect(summary("summary-a").classList.contains("line-clamp-2")).toBe(true);
    expect(toggle("summary-a").textContent).toBe("Show more");
  });
});
