/**
 * Text fields from a submitted form. A field holding an uploaded File is treated as
 * missing: calling toString() on it would yield the text "[object File]".
 */

/** The field's text, "" for an empty field, or undefined when it is absent or a File. */
export function formText(formData: FormData, name: string): string | undefined {
  const value = formData.get(name);
  return typeof value === "string" ? value : undefined;
}

/** Every text value submitted under the name, in order; Files are dropped. */
export function formTexts(formData: FormData, name: string): string[] {
  return formData.getAll(name).filter((value) => typeof value === "string");
}
