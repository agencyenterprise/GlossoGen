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

/** Format a scenario config value for full-text modal display. */
export function formatConfigValueFull(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Format a cost in USD. Shows 2 decimals for >= $0.01, 4 decimals for sub-cent. */
export function formatCost(usd: number): string {
  if (usd <= 0) {
    return "--";
  }
  if (usd < 0.01) {
    return `$${usd.toFixed(4)}`;
  }
  return `$${usd.toFixed(2)}`;
}

/** Format seconds into a human-readable duration like "2m 30s" or "1h 5m". */
export function formatDuration(seconds: number): string {
  const totalSeconds = Math.round(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

/** Compute elapsed seconds since an ISO timestamp. */
export function elapsedSince(isoTimestamp: string): number {
  return (Date.now() - new Date(isoTimestamp).getTime()) / 1000;
}

const PRIORITY_CONFIG_KEYS = [
  "two_teams",
  "swap_round",
  "announce_swap",
  "postmortem_enabled",
  "postmortem_after_swap",
  "intern_enabled",
  "intern_join_round",
  "intern_takeover_round",
];

/** Sort scenario_config entries with mode-defining intern/swap knobs first, then the rest in insertion order. */
export function sortConfigEntries(entries: Array<[string, unknown]>): Array<[string, unknown]> {
  const priorityIndex = new Map<string, number>();
  PRIORITY_CONFIG_KEYS.forEach((key, index) => priorityIndex.set(key, index));

  const priority: Array<[string, unknown]> = [];
  const rest: Array<[string, unknown]> = [];
  for (const entry of entries) {
    if (priorityIndex.has(entry[0])) {
      priority.push(entry);
    } else {
      rest.push(entry);
    }
  }
  priority.sort((a, b) => priorityIndex.get(a[0])! - priorityIndex.get(b[0])!);
  return [...priority, ...rest];
}
