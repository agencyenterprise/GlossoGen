"use client";

import { Bot } from "lucide-react";
import type { components } from "@/types/api.gen";
import { HeaderDropdown } from "./header-dropdown";
import { countAgentModels, formatModelCounts } from "./run-row-details";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];

/** The models a run's agents played, as a dropdown beside Run info and Knobs:
 *  the trigger names every model that played, the panel says which agent
 *  played which, and from which round when a swap or replacement changed it.
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
        <div className="space-y-1">
          {agentModels.map(agent => (
            <div key={agent.agent_id} className="flex justify-between gap-6">
              <span className="text-muted-foreground">{agent.role_name}</span>
              <span className="flex flex-col items-end">
                {agent.played.map((played, index) => (
                  <span key={`${index}-${played.from_round}`} className="font-mono text-foreground">
                    {index > 0 ? (
                      <span className="mr-1.5 font-sans text-[11px] text-muted-foreground">
                        from R{played.from_round}
                      </span>
                    ) : null}
                    {played.provider}:{played.model}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      )}
    </HeaderDropdown>
  );
}
