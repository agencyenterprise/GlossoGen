"use client";

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import { humanize } from "./format";

type AgentDetail = components["schemas"]["AgentDetail"];

interface RunSidebarProps {
  channelIds: string[];
  agents: AgentDetail[];
  selectedChannel: string | null;
  selectedAgent: string | null;
  showLogs: boolean;
  showEvalLogs: boolean;
  hasLogs: boolean;
  hasEvalLogs: boolean;
  agentColorMap: Map<string, AgentColor>;
  onSelectChannel: (channelId: string | null) => void;
  onSelectAgent: (agentId: string) => void;
  onSelectLogs: () => void;
  onSelectEvalLogs: () => void;
}

export function RunSidebar({
  channelIds,
  agents,
  selectedChannel,
  selectedAgent,
  showLogs,
  showEvalLogs,
  hasLogs,
  hasEvalLogs,
  agentColorMap,
  onSelectChannel,
  onSelectAgent,
  onSelectLogs,
  onSelectEvalLogs,
}: RunSidebarProps) {
  return (
    <div className="flex flex-col overflow-y-auto border-r border-border bg-muted/50 py-4">
      <div className="mb-5">
        <div className="mb-1 px-3.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Channels
        </div>
        <button
          className={cn(
            "flex w-full items-center gap-2 px-3.5 py-1.5 text-[13px] transition-colors hover:bg-accent/50",
            selectedChannel === null &&
              !selectedAgent &&
              !showLogs &&
              "bg-accent font-medium text-foreground"
          )}
          onClick={() => onSelectChannel(null)}
        >
          <span className="opacity-50">⏱</span> all activity
        </button>
        {channelIds.map(id => (
          <button
            key={id}
            className={cn(
              "flex w-full items-center gap-2 px-3.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent/50",
              selectedChannel === id &&
                !selectedAgent &&
                !showLogs &&
                "bg-accent font-medium text-foreground"
            )}
            onClick={() => onSelectChannel(id)}
          >
            <span className="opacity-50">#</span> {humanize(id)}
          </button>
        ))}
      </div>

      <div className="mx-3.5 mb-4 h-px bg-border" />

      <div>
        <div className="mb-1 px-3.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Agents
        </div>
        {agents.map(agent => {
          const color = agentColorMap.get(agent.agent_id);
          return (
            <button
              key={agent.agent_id}
              className={cn(
                "flex w-full items-center gap-2 px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent/50",
                selectedAgent === agent.agent_id && "bg-accent font-medium text-foreground"
              )}
              onClick={() => onSelectAgent(agent.agent_id)}
            >
              <div
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded text-[8px] font-semibold",
                  color?.bg,
                  color?.fg
                )}
              >
                {deriveInitials(agent.role_name)}
              </div>
              {agent.role_name}
            </button>
          );
        })}
      </div>

      {hasLogs || hasEvalLogs ? (
        <>
          <div className="mx-3.5 mb-4 mt-4 h-px bg-border" />
          <div>
            {hasLogs ? (
              <button
                className={cn(
                  "flex w-full items-center gap-2 px-3.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent/50",
                  showLogs && "bg-accent font-medium text-foreground"
                )}
                onClick={onSelectLogs}
              >
                <span className="opacity-50">{">"}_</span> Logs
              </button>
            ) : null}
            {hasEvalLogs ? (
              <button
                className={cn(
                  "flex w-full items-center gap-2 px-3.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent/50",
                  showEvalLogs && "bg-accent font-medium text-foreground"
                )}
                onClick={onSelectEvalLogs}
              >
                <span className="opacity-50">{">"}_</span> Eval logs
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </div>
  );
}
