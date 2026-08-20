/**
 * The message a failed API call should show.
 *
 * FastAPI answers two shapes. A handler's own refusal puts a sentence in `detail`,
 * and those sentences are worth reading: "this selection is 6000 runs, the limit is
 * 5000", "this group already has a dashboard called 'Noise sweep'". A body that fails
 * validation puts a list of errors there instead, one per field, and reading only the
 * string shape turns every one of those into a bare fallback with no hint of which
 * field was wrong.
 */

interface ValidationEntry {
  loc?: unknown;
  msg?: unknown;
}

function fieldPath(entry: ValidationEntry): string {
  if (!Array.isArray(entry.loc)) {
    return "";
  }
  // The first element is always the source ("body"), which says nothing here.
  return entry.loc.slice(1).join(".");
}

function validationMessage(entries: unknown[]): string | null {
  const lines = entries
    .filter((entry): entry is ValidationEntry => typeof entry === "object" && entry !== null)
    .map(entry => {
      const message = typeof entry.msg === "string" ? entry.msg : "is not valid";
      const path = fieldPath(entry);
      return path === "" ? message : `${path}: ${message}`;
    });
  return lines.length === 0 ? null : lines.join("; ");
}

function detailOf(error: unknown): string | null {
  if (!error || typeof error !== "object" || !("detail" in error)) {
    return null;
  }
  const detail = (error as { detail: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return validationMessage(detail);
  }
  return null;
}

/** Throw the server's own reason, or `fallback` when it gave none. */
export function apiError(error: unknown, fallback: string): Error {
  return new Error(detailOf(error) ?? fallback);
}
