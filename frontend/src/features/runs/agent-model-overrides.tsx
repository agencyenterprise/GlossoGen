"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { ModelPicker } from "./model-picker";

export type AgentModelOverride = { model: string; provider: string };

export function AgentModelOverrides({
  agents,
  models,
  overrides,
  onChange,
}: {
  agents: { agent_id: string; role_name: string }[];
  models: { model_prefix: string; provider: string }[];
  overrides: Record<string, AgentModelOverride>;
  onChange: (updated: Record<string, AgentModelOverride>) => void;
}) {
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);

  function handleSelect(args: {
    agentId: string;
    selectedModel: string;
    selectedProvider: string;
  }) {
    onChange({
      ...overrides,
      [args.agentId]: { model: args.selectedModel, provider: args.selectedProvider },
    });
    setExpandedAgent(null);
  }

  function handleClear(agentId: string) {
    const next = { ...overrides };
    delete next[agentId];
    onChange(next);
    setExpandedAgent(null);
  }

  return (
    <div className="space-y-1">
      {agents.map(agent => {
        const override = overrides[agent.agent_id];
        const isExpanded = expandedAgent === agent.agent_id;

        return (
          <div key={agent.agent_id} className="rounded border border-border bg-muted/20 px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">{agent.role_name}</span>
              <div className="flex items-center gap-2">
                {override ? (
                  <>
                    <span className="text-xs text-primary">
                      {override.provider}/{override.model}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleClear(agent.agent_id)}
                      className="text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setExpandedAgent(isExpanded ? null : agent.agent_id)}
                    className="text-xs text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {isExpanded ? "Cancel" : "Override"}
                  </button>
                )}
              </div>
            </div>
            {isExpanded ? (
              <div className="mt-2">
                <ModelPicker
                  models={models}
                  selectedModel=""
                  onSelect={(selectedModel, selectedProvider) =>
                    handleSelect({
                      agentId: agent.agent_id,
                      selectedModel,
                      selectedProvider,
                    })
                  }
                />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
