export function humanize(value: string): string {
  return value
    .split(/[-_]/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Format a scenario config value for display in a badge. */
export function formatConfigValue(value: unknown): string {
  if (Array.isArray(value)) {
    return `${value.length} items`;
  }
  if (typeof value === "object" && value !== null) {
    const json = JSON.stringify(value);
    if (json.length > 60) {
      return json.slice(0, 57) + "...";
    }
    return json;
  }
  return String(value);
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
