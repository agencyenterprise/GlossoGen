"use client";

import { Bot } from "lucide-react";
import type { components } from "@/types/api.gen";
import { HeaderDropdown } from "./header-dropdown";
import { countAgentModels, formatModelCounts } from "./run-row-details";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];

/** The models a run's agents played, as a dropdown beside Run info and Knobs:
 *  the trigger names the models, the panel says which agent played which.
 *  Renders nothing for a run that recorded no agents. */
export function AgentModelsDropdown({
  agentModels,
  align,
}: {
  agentModels: AgentModelSummary[];
  align: "left" | "right";
}) {
  const counts = countAgentModels(agentModels);
  if (counts.length === 0) {
    return null;
  }
  return (
    <HeaderDropdown
      label={formatModelCounts(counts)}
      icon={<Bot className="h-3 w-3" />}
      badge={null}
      align={align}
      panelClassName="w-max min-w-56 p-3"
    >
      {() => (
        <div className="space-y-0.5">
          {agentModels.map(agent => (
            <div key={agent.agent_id} className="flex justify-between gap-6">
              <span className="text-muted-foreground">{agent.role_name}</span>
              <span className="font-mono text-foreground">
                {agent.provider}:{agent.model}
              </span>
            </div>
          ))}
        </div>
      )}
    </HeaderDropdown>
  );
}
