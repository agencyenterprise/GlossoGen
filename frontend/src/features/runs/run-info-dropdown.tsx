"use client";

import { Info } from "lucide-react";
import type { components } from "@/types/api.gen";
import { formatCost, formatDayHeader, formatDuration, formatTokens } from "./format";
import { HeaderDropdown } from "./header-dropdown";

type AgentTokenUsage = components["schemas"]["AgentTokenUsageResponse"];

type Stat = {
  label: string;
  value: string;
};

function buildStats({
  timestamp,
  roundCount,
  messageCount,
  eventCount,
  agentCount,
  totalCostUsd,
  durationSeconds,
  tokenUsage,
}: {
  timestamp: string;
  roundCount: number;
  messageCount: number;
  eventCount: number | null;
  agentCount: number;
  totalCostUsd: number;
  durationSeconds: number;
  tokenUsage: AgentTokenUsage | null;
}): Stat[] {
  const stats: Stat[] = [
    { label: "Started", value: formatDayHeader(timestamp) },
    { label: "Rounds", value: String(roundCount) },
    { label: "Messages", value: String(messageCount) },
  ];
  if (eventCount !== null) {
    stats.push({ label: "Events", value: String(eventCount) });
  }
  stats.push({ label: "Agents", value: String(agentCount) });
  if (totalCostUsd > 0) {
    stats.push({ label: "Cost", value: formatCost(totalCostUsd) });
  }
  if (durationSeconds > 0) {
    stats.push({ label: "Duration", value: formatDuration(durationSeconds) });
  }
  if (tokenUsage === null) {
    return stats;
  }
  if (tokenUsage.input_tokens > 0) {
    stats.push({ label: "Input tokens", value: formatTokens(tokenUsage.input_tokens) });
  }
  if (tokenUsage.output_tokens > 0) {
    stats.push({ label: "Output tokens", value: formatTokens(tokenUsage.output_tokens) });
  }
  // Part of the output count, so it is shown as a share of it rather than a
  // separate total. A provider reporting no breakdown leaves it at 0, which
  // reads the same as a model that did not think, so the row is left out.
  if (tokenUsage.reasoning_tokens > 0) {
    const share = Math.round((tokenUsage.reasoning_tokens / tokenUsage.output_tokens) * 100);
    stats.push({
      label: "of which thinking",
      value: `${formatTokens(tokenUsage.reasoning_tokens)} (${share}%)`,
    });
  }
  return stats;
}

/**
 * The run header's "Run info" dropdown: start date, round / message / event /
 * agent counts, cost, duration and token counts.
 *
 * ``eventCount`` is ``null`` for surfaces that carry no timeline entry count
 * (the public demo viewer, the runs list), which drops the Events row.
 * ``tokenUsage`` is ``null`` where the surface carries none (the runs list),
 * which drops the token rows. ``align`` is passed through to
 * :func:`HeaderDropdown`: "right" in a run header, "left" in a runs-list row.
 */
export function RunInfoDropdown({
  timestamp,
  roundCount,
  messageCount,
  eventCount,
  agentCount,
  totalCostUsd,
  durationSeconds,
  tokenUsage,
  align,
}: {
  timestamp: string;
  roundCount: number;
  messageCount: number;
  eventCount: number | null;
  agentCount: number;
  totalCostUsd: number;
  durationSeconds: number;
  tokenUsage: AgentTokenUsage | null;
  align: "left" | "right";
}) {
  const stats = buildStats({
    timestamp,
    roundCount,
    messageCount,
    eventCount,
    agentCount,
    totalCostUsd,
    durationSeconds,
    tokenUsage,
  });

  return (
    <HeaderDropdown
      label="Run info"
      icon={<Info className="h-3 w-3" />}
      badge={null}
      align={align}
      panelClassName="w-max min-w-56 p-3"
    >
      {() => (
        <dl className="space-y-1">
          {stats.map(stat => (
            <div key={stat.label} className="flex justify-between gap-6">
              <dt className="text-muted-foreground">{stat.label}</dt>
              <dd className="font-medium text-foreground">{stat.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </HeaderDropdown>
  );
}
