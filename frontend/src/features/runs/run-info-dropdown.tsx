"use client";

import { Info } from "lucide-react";
import type { components } from "@/types/api.gen";
import { formatCost, formatDayHeader, formatDuration } from "./format";
import { HeaderDropdown } from "./header-dropdown";

type AgentDetail = components["schemas"]["AgentDetail"];

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
}: {
  timestamp: string;
  roundCount: number;
  messageCount: number;
  eventCount: number | null;
  agentCount: number;
  totalCostUsd: number;
  durationSeconds: number;
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
  return stats;
}

/**
 * The run header's "Run info" dropdown: start date, round / message / event /
 * agent counts, cost, duration, and the per-agent model roster.
 *
 * ``eventCount`` is ``null`` for surfaces that carry no timeline entry count
 * (the public demo viewer), which drops the Events row.
 */
export function RunInfoDropdown({
  timestamp,
  roundCount,
  messageCount,
  eventCount,
  agents,
  totalCostUsd,
  durationSeconds,
  modelLabel,
}: {
  timestamp: string;
  roundCount: number;
  messageCount: number;
  eventCount: number | null;
  agents: AgentDetail[];
  totalCostUsd: number;
  durationSeconds: number;
  modelLabel: string;
}) {
  const stats = buildStats({
    timestamp,
    roundCount,
    messageCount,
    eventCount,
    agentCount: agents.length,
    totalCostUsd,
    durationSeconds,
  });

  return (
    <HeaderDropdown
      label="Run info"
      icon={<Info className="h-3 w-3" />}
      badge={null}
      align="right"
      panelClassName="w-max min-w-56 p-3"
    >
      {() => (
        <>
          <dl className="space-y-1">
            {stats.map(stat => (
              <div key={stat.label} className="flex justify-between gap-6">
                <dt className="text-muted-foreground">{stat.label}</dt>
                <dd className="font-medium text-foreground">{stat.value}</dd>
              </div>
            ))}
          </dl>
          {agents.length > 0 ? (
            <div className="mt-2 border-t border-border pt-2">
              <div className="flex justify-between gap-6">
                <span className="text-muted-foreground">Models</span>
                <span className="font-medium text-foreground">{modelLabel}</span>
              </div>
              <div className="mt-1 space-y-0.5">
                {agents.map(agent => (
                  <div key={agent.agent_id} className="flex justify-between gap-6">
                    <span className="text-muted-foreground">{agent.role_name}</span>
                    <span className="font-mono text-foreground">
                      {agent.provider}:{agent.model}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </HeaderDropdown>
  );
}
