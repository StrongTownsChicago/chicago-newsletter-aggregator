import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initConfirmedSubmits } from "../../client/confirmed-submits";

describe("initConfirmedSubmits", () => {
  let submitted: boolean;

  beforeEach(() => {
    document.body.innerHTML = `
      <form><button type="submit" data-confirm="Delete this rule?">Delete</button></form>`;
    submitted = false;
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      submitted = true;
    });
    initConfirmedSubmits();
  });

  afterEach(() => vi.unstubAllGlobals());

  it.each([
    [true, true],
    [false, false],
  ])("submits only when the visitor accepts (accepted: %s)", (accepted, expectSubmitted) => {
    const confirm = vi.fn(() => accepted);
    vi.stubGlobal("confirm", confirm);

    document.querySelector("button")!.click();

    expect(confirm).toHaveBeenCalledWith("Delete this rule?");
    expect(submitted).toBe(expectSubmitted);
  });
});
