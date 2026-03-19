"use client";

import { useMemo, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { EvidenceModal } from "./evidence-modal";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { VerdictPill } from "./verdict-pill";

interface DrawerTurnGroup {
  turnNumber: number;
  timestamp: string;
  entries: DisplayEntry[];
}

function groupByTurn(messages: DisplayEntry[]): DrawerTurnGroup[] {
  const groups: DrawerTurnGroup[] = [];
  let current: DrawerTurnGroup | null = null;

  for (const msg of messages) {
    if (current && msg.turn_number === current.turnNumber) {
      current.entries.push(msg);
    } else {
      if (current) {
        groups.push(current);
      }
      current = {
        turnNumber: msg.turn_number,
        timestamp: msg.timestamp,
        entries: [msg],
      };
    }
  }
  if (current) {
    groups.push(current);
  }
  return groups;
}

type AgentDetail = components["schemas"]["AgentDetail"];
type EvalMetricResponse = components["schemas"]["EvalMetricResponse"];

type DrawerTab = "prompt" | "messages" | "verdicts";

interface AgentDrawerProps {
  agent: AgentDetail;
  messages: DisplayEntry[];
  agentColor: AgentColor;
  channelColorMap: Map<string, AgentColor>;
  onClose: () => void;
  onNavigateToMessage: (messageId: string, channelId: string) => void;
  onNavigateToChannel: (channelId: string) => void;
  evalMetrics: EvalMetricResponse[] | null;
}

export function AgentDrawer({
  agent,
  messages,
  agentColor,
  channelColorMap,
  onClose,
  onNavigateToMessage,
  onNavigateToChannel,
  evalMetrics,
}: AgentDrawerProps) {
  const [activeTab, setActiveTab] = useState<DrawerTab>("prompt");
  const [expandedMetric, setExpandedMetric] = useState<EvalMetricResponse | null>(null);
  const agentMessages = messages.filter(m => m.sender_agent_id === agent.agent_id);
  const turnGroups = useMemo(() => groupByTurn(agentMessages), [agentMessages]);

  return (
    <div className="absolute inset-y-0 right-0 z-10 flex w-[calc(100%-192px)] flex-col border-l border-border bg-background">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-3 border-b border-border px-5 py-3">
        <div
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-xs font-semibold",
            agentColor.bg,
            agentColor.fg
          )}
        >
          {deriveInitials(agent.role_name)}
        </div>
        <div>
          <div className="text-[15px] font-medium">{agent.role_name}</div>
          <div className="text-[11px] text-muted-foreground">{agent.model}</div>
        </div>
        <button
          aria-label="Close"
          className="ml-auto rounded p-1 text-muted-foreground transition-colors hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 border-b border-border px-5">
        <TabButton active={activeTab === "prompt"} onClick={() => setActiveTab("prompt")}>
          System prompt
        </TabButton>
        <TabButton active={activeTab === "messages"} onClick={() => setActiveTab("messages")}>
          Messages ({agentMessages.length})
        </TabButton>
        {evalMetrics ? (
          <TabButton active={activeTab === "verdicts"} onClick={() => setActiveTab("verdicts")}>
            Verdicts
          </TabButton>
        ) : null}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "prompt" ? (
          <div className="p-5">
            <ProseMarkdown className="rounded-lg bg-muted/50 p-3">
              {agent.system_prompt}
            </ProseMarkdown>
          </div>
        ) : null}
        {activeTab === "messages" ? (
          <div className="py-2">
            {turnGroups.map((turn, turnIdx) => (
              <div key={`${turnIdx}-${turn.turnNumber}`} className="flex gap-2.5 px-5 py-2">
                <div className="flex w-5 shrink-0 flex-col items-center justify-center">
                  <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                    {turn.turnNumber}
                  </span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="mb-1">
                    <span className="text-[10px] text-muted-foreground">
                      {formatTime(turn.timestamp)}
                    </span>
                  </div>
                  {turn.entries.map(entry => {
                    const entryChColor = channelColorMap.get(entry.channel_id);
                    return (
                      <div
                        key={entry.message_id}
                        className={cn(entry.is_reasoning && "ml-4 opacity-50")}
                      >
                        {entry.is_reasoning ? (
                          <span className="text-[10px] italic text-muted-foreground">
                            reasoning
                          </span>
                        ) : (
                          <span className="mb-0.5 flex items-baseline gap-1.5">
                            <button
                              className={cn(
                                "cursor-pointer rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed hover:underline",
                                entryChColor?.bg,
                                entryChColor?.fg
                              )}
                              onClick={() => onNavigateToChannel(entry.channel_id)}
                            >
                              #{entry.channel_id}
                            </button>
                            <button
                              className="cursor-pointer text-[10px] text-muted-foreground hover:underline"
                              onClick={() =>
                                onNavigateToMessage(entry.message_id, entry.channel_id)
                              }
                            >
                              jump
                            </button>
                          </span>
                        )}
                        <ProseMarkdown>{entry.text}</ProseMarkdown>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {activeTab === "verdicts" && evalMetrics ? (
          <div className="space-y-0 divide-y divide-border px-5 py-3">
            {evalMetrics.map(metric => {
              const agentVerdict = metric.per_agent[agent.agent_id];
              if (!agentVerdict) {
                return null;
              }
              return (
                <button
                  key={metric.evaluator_name}
                  className="block w-full rounded-md py-2.5 text-left transition-colors hover:bg-muted/50"
                  onClick={() => setExpandedMetric(metric)}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">{humanize(metric.evaluator_name)}</span>
                    <VerdictPill verdict={agentVerdict} />
                  </div>
                  {metric.evidence.length > 0 ? (
                    <ProseMarkdown className="mt-1 line-clamp-3 [&_p]:my-0">
                      {metric.evidence[0]!}
                    </ProseMarkdown>
                  ) : null}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>

      {expandedMetric ? (
        <EvidenceModal metric={expandedMetric} onClose={() => setExpandedMetric(null)} />
      ) : null}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      className={cn(
        "-mb-px border-b-2 px-3 py-2 text-xs transition-colors",
        active
          ? "border-foreground text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      )}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
