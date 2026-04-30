"use client";

import { useMemo, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { EvidenceModal } from "./evidence-modal";
import { formatTime, humanize } from "./format";
import { NotificationDisplay } from "./notification-display";
import { ProseMarkdown } from "./prose-markdown";
import { ToolCallDisplay } from "./tool-call-display";

interface DrawerTurnGroup {
  timestamp: string;
  entries: DisplayEntry[];
}

function groupByTurn(messages: DisplayEntry[]): DrawerTurnGroup[] {
  const groups: DrawerTurnGroup[] = [];
  let current: DrawerTurnGroup | null = null;

  for (const msg of messages) {
    if (current) {
      current.entries.push(msg);
    } else {
      current = {
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
type MeasurementResponse = components["schemas"]["MeasurementResponse"];

type DrawerTab = "prompt" | "messages" | "metrics";

interface AgentDrawerProps {
  agent: AgentDetail;
  messages: DisplayEntry[];
  agentColor: AgentColor;
  channelColorMap: Map<string, AgentColor>;
  onClose: () => void;
  onNavigateToMessage: (messageId: string, channelId: string) => void;
  onNavigateToChannel: (channelId: string) => void;
  measurements: MeasurementResponse[] | null;
}

export function AgentDrawer({
  agent,
  messages,
  agentColor,
  channelColorMap,
  onClose,
  onNavigateToMessage,
  onNavigateToChannel,
  measurements,
}: AgentDrawerProps) {
  const [activeTab, setActiveTab] = useState<DrawerTab>("prompt");
  const [expandedMeasurement, setExpandedMeasurement] = useState<MeasurementResponse | null>(null);
  const agentMessages = messages.filter(m => m.sender_agent_id === agent.agent_id);
  const turnGroups = useMemo(() => groupByTurn(agentMessages), [agentMessages]);
  const agentMetrics = (measurements ?? []).flatMap(measurement => {
    const observations = measurement.per_agent.filter(obs => obs.agent_id === agent.agent_id);
    if (observations.length === 0) {
      return [];
    }
    return observations.map(obs => ({ measurement, observation: obs }));
  });

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
        {agentMetrics.length > 0 ? (
          <TabButton active={activeTab === "metrics"} onClick={() => setActiveTab("metrics")}>
            Metrics ({agentMetrics.length})
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
              <div key={turnIdx} className="flex gap-2.5 px-5 py-2">
                <div className="flex w-5 shrink-0 flex-col items-center justify-center">
                  <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                    {turnIdx + 1}
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
                        className={cn(
                          entry.is_reasoning &&
                            "ml-4 rounded-md border border-border/60 bg-muted/35 px-2 py-1.5 text-muted-foreground dark:bg-muted/20",
                          !entry.is_reasoning &&
                            !entry.is_tool_use &&
                            !entry.is_notification_result &&
                            "rounded-md border border-border/70 bg-background px-2 py-1.5 shadow-sm",
                          (entry.is_tool_use || entry.is_notification_result) && "ml-4"
                        )}
                      >
                        {entry.is_reasoning ? (
                          <span className="mb-1 inline-block rounded-full border border-border/70 bg-background/80 px-1.5 py-px text-[10px] font-medium text-muted-foreground">
                            reasoning
                          </span>
                        ) : entry.is_tool_use || entry.is_notification_result ? null : (
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
                        {entry.is_notification_result ? (
                          <NotificationDisplay result={entry.tool_result} />
                        ) : entry.is_tool_use ? (
                          <ToolCallDisplay
                            toolName={entry.tool_name}
                            arguments={entry.tool_arguments}
                            result={entry.tool_result}
                            stabilizeMetadata={entry.stabilize_metadata}
                          />
                        ) : (
                          <ProseMarkdown className={cn(!entry.is_reasoning && "text-foreground")}>
                            {entry.text}
                          </ProseMarkdown>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {activeTab === "metrics" && agentMetrics.length > 0 ? (
          <div className="space-y-0 divide-y divide-border px-5 py-3">
            {agentMetrics.map(({ measurement, observation }) => (
              <button
                key={`${measurement.metric_name}::${observation.agent_id}`}
                className="block w-full rounded-md py-2.5 text-left transition-colors hover:bg-muted/50"
                onClick={() => setExpandedMeasurement(measurement)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium">{humanize(measurement.metric_name)}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {observation.value.toFixed(2)}
                  </span>
                </div>
                {observation.note ? (
                  <span className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                    {observation.note}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {expandedMeasurement ? (
        <EvidenceModal
          measurement={expandedMeasurement}
          onClose={() => setExpandedMeasurement(null)}
        />
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
