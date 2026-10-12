/**
 * How a seat's harness is shown: a badge beside its model, and a suffix on the
 * model's tooltip.
 *
 * Only a seat outside the default harness is marked, so a run whose every seat
 * ran under pydantic-ai looks the same as before harnesses were recorded.
 */

export const DEFAULT_HARNESS = "pydantic-ai";

const HARNESS_LABELS: Record<string, string> = {
  "claude-agent-sdk": "Claude Code",
  codex: "Codex",
};

/** The harness's display name; a harness from another package shows under its own name. */
export function harnessLabel(harness: string): string {
  return HARNESS_LABELS[harness] ?? harness;
}

/** `provider/model`, followed by the harness when the seat ran outside the default one. */
export function seatDescription({
  provider,
  model,
  harness,
}: {
  provider: string;
  model: string;
  harness: string;
}): string {
  const base = `${provider}/${model}`;
  if (harness === DEFAULT_HARNESS) {
    return base;
  }
  return `${base} · ${harnessLabel(harness)}`;
}

/** The badge's tooltip: the harness, and the CLI session ids the seat was bound to. */
export function harnessBadgeTitle(harness: string, sessionIds: string[]): string {
  const base = `Ran under the ${harness} harness`;
  if (sessionIds.length === 0) {
    return base;
  }
  return `${base}; session ${sessionIds.join(", ")}`;
}

export function HarnessBadge({ harness, sessionIds }: { harness: string; sessionIds: string[] }) {
  if (harness === DEFAULT_HARNESS) {
    return null;
  }
  return (
    <span
      title={harnessBadgeTitle(harness, sessionIds)}
      className="inline-flex items-center rounded-full bg-violet-500/15 px-1.5 py-0.5 font-sans text-[10px] font-medium text-violet-700 dark:text-violet-300"
    >
      {harnessLabel(harness)}
    </span>
  );
}
