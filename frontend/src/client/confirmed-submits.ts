// Client wiring for submit buttons that ask before a destructive action.

/** Cancels the submit of every button with data-confirm unless the visitor accepts its message. */
export function initConfirmedSubmits(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("button[data-confirm]")) {
    button.addEventListener("click", (event) => {
      if (!window.confirm(button.dataset.confirm ?? "")) event.preventDefault();
    });
  }
}
