"use client";

import { Bot } from "lucide-react";
import type { components } from "@/types/api.gen";
import { HoverPopover } from "./hover-popover";
import { countAgentModels, formatModelCounts } from "./run-row-details";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];

/** The models a run's agents played, as one short line, whose hover popover
 *  says which agent played which model. Renders nothing for a run that
 *  recorded no agents. */
export function AgentModelsBadge({ agentModels }: { agentModels: AgentModelSummary[] }) {
  const counts = countAgentModels(agentModels);
  if (counts.length === 0) {
    return null;
  }
  return (
    <HoverPopover
      triggerClassName="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0 font-mono text-[10px] text-muted-foreground"
      trigger={
        <>
          <Bot className="h-2.5 w-2.5" />
          {formatModelCounts(counts)}
        </>
      }
      layoutKey={agentModels}
    >
      <div className="space-y-0.5">
        {agentModels.map(agent => (
          <div key={agent.agent_id} className="flex items-baseline justify-between gap-6">
            <span className="text-muted-foreground">{agent.role_name}</span>
            <span className="font-mono text-foreground">
              {agent.provider}:{agent.model}
            </span>
          </div>
        ))}
      </div>
    </HoverPopover>
  );
}
