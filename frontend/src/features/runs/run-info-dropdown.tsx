"use client";

import { Info } from "lucide-react";
import type { components } from "@/types/api.gen";
import {
  formatCost,
  formatDayHeader,
  formatDuration,
  formatModelSettings,
  formatTokens,
} from "./format";
import { HeaderDropdown } from "./header-dropdown";

type AgentDetail = components["schemas"]["AgentDetail"];
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
  tokenUsage: AgentTokenUsage;
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
 * agent counts, cost, duration, token counts, and the per-agent model roster.
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
  tokenUsage,
  modelLabel,
}: {
  timestamp: string;
  roundCount: number;
  messageCount: number;
  eventCount: number | null;
  agents: AgentDetail[];
  totalCostUsd: number;
  durationSeconds: number;
  tokenUsage: AgentTokenUsage;
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
    tokenUsage,
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
                    <span className="text-right font-mono text-foreground">
                      {agent.provider}:{agent.model}
                      <span className="block text-[11px] text-muted-foreground">
                        {formatModelSettings(agent.model_settings)}
                      </span>
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
