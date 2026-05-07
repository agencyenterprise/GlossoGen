"use client";

import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { AgentInstance } from "./agent-instance";
import { humanize } from "./format";

type AgentDetail = components["schemas"]["AgentDetail"];

interface RunSidebarProps {
  channelIds: string[];
  agents: AgentDetail[];
  agentInstances: AgentInstance[];
  selectedChannel: string | null;
  selectedAgent: string | null;
  showLogs: boolean;
  showEvalLogs: boolean;
  hasLogs: boolean;
  hasEvalLogs: boolean;
  agentColorMap: Map<string, AgentColor>;
  onSelectChannel: (channelId: string | null) => void;
  onSelectAgent: (instanceKey: string) => void;
  onSelectLogs: () => void;
  onSelectEvalLogs: () => void;
}

function formatRoundRange(instance: AgentInstance): string {
  if (instance.round_end === null) {
    return `r${instance.round_start}-…`;
  }
  if (instance.round_start === instance.round_end) {
    return `r${instance.round_start}`;
  }
  return `r${instance.round_start}-${instance.round_end}`;
}

export function RunSidebar({
  channelIds,
  agents,
  agentInstances,
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
          const instances = agentInstances.filter(i => i.agent_id === agent.agent_id);
          // Single-instance agents render as today (no children, no extra chrome).
          if (instances.length <= 1) {
            const instance = instances[0];
            const instanceKey = instance ? instance.instance_key : `${agent.agent_id}:1`;
            return (
              <button
                key={agent.agent_id}
                title={`${agent.provider}/${agent.model}`}
                className={cn(
                  "flex w-full items-center gap-2 px-3.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent/50",
                  selectedAgent === instanceKey && "bg-accent font-medium text-foreground"
                )}
                onClick={() => onSelectAgent(instanceKey)}
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
          }
          // Multiple generations: parent label + indented Gen sub-rows.
          return (
            <div key={agent.agent_id} className="mb-1">
              <div className="flex items-center gap-2 px-3.5 py-1 text-xs text-muted-foreground">
                <div
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded text-[8px] font-semibold",
                    color?.bg,
                    color?.fg
                  )}
                >
                  {deriveInitials(agent.role_name)}
                </div>
                <span className="font-medium">{agent.role_name}</span>
              </div>
              <div className={cn("ml-3 border-l-2 pl-2", color?.bg ?? "border-border")}>
                {instances.map(instance => {
                  const isLive = instance.is_latest && instance.round_end === null;
                  return (
                    <button
                      key={instance.instance_key}
                      title={`${instance.provider}/${instance.model}`}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 rounded-r px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent/50",
                        selectedAgent === instance.instance_key &&
                          "bg-accent font-medium text-foreground"
                      )}
                      onClick={() => onSelectAgent(instance.instance_key)}
                    >
                      <span className="flex items-center gap-1.5">
                        <span>Gen {instance.generation}</span>
                        {isLive ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-1.5 py-px text-[9px] font-medium text-emerald-700 dark:text-emerald-400">
                            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                            live
                          </span>
                        ) : null}
                      </span>
                      <span className="text-[10px] tabular-nums opacity-70">
                        {formatRoundRange(instance)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
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
