"use client";

import { type ReactNode } from "react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import type { AgentColor } from "./agent-colors";

type AgentDetail = components["schemas"]["AgentDetail"];

/**
 * The channel-chat header bar: channel name + description, per-member focus
 * toggles, the reasoning / tools visibility checkboxes, and the caller-provided
 * export controls. Purely presentational — all state lives in ``ChatPane``.
 */
export function ChatHeader({
  headerName,
  headerDesc,
  channelMembers,
  focusedAgentIds,
  onToggleFocusedAgent,
  agentColorMap,
  showReasoning,
  onShowReasoningChange,
  showTools,
  onShowToolsChange,
  exportSlot,
}: {
  headerName: string;
  headerDesc: string;
  channelMembers: AgentDetail[];
  focusedAgentIds: Set<string>;
  onToggleFocusedAgent: (agentId: string) => void;
  agentColorMap: Map<string, AgentColor>;
  showReasoning: boolean;
  onShowReasoningChange: (value: boolean) => void;
  showTools: boolean;
  onShowToolsChange: (value: boolean) => void;
  exportSlot: ReactNode;
}) {
  return (
    <div
      id="chat-channel-header"
      className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5"
    >
      <span className="text-sm text-muted-foreground">#</span>
      <span className="text-[13px] font-medium">{headerName}</span>
      <span className="text-xs text-muted-foreground">{headerDesc}</span>
      {channelMembers.length > 0 ? (
        <div className="ml-auto flex flex-wrap items-center gap-1">
          {channelMembers.map(member => {
            const isFocused = focusedAgentIds.has(member.agent_id);
            const color = agentColorMap.get(member.agent_id);
            return (
              <button
                key={member.agent_id}
                type="button"
                aria-pressed={isFocused}
                title={
                  isFocused
                    ? `Showing only ${member.role_name} — click to clear`
                    : `Show only ${member.role_name}`
                }
                onClick={() => onToggleFocusedAgent(member.agent_id)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                  isFocused
                    ? cn("border-transparent font-medium", color?.bg, color?.fg)
                    : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"
                )}
              >
                {member.role_name}
              </button>
            );
          })}
        </div>
      ) : null}
      <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground select-none">
        <input
          type="checkbox"
          checked={showReasoning}
          onChange={e => onShowReasoningChange(e.target.checked)}
          className="h-3 w-3 rounded border-border accent-foreground"
        />
        Reasoning
      </label>
      <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground select-none">
        <input
          type="checkbox"
          checked={showTools}
          onChange={e => onShowToolsChange(e.target.checked)}
          className="h-3 w-3 rounded border-border accent-foreground"
        />
        Tools
      </label>
      {exportSlot}
    </div>
  );
}
