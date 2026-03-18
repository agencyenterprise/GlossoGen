"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import { EvidenceModal } from "./evidence-modal";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { VerdictPill } from "./verdict-pill";

type AgentDetail = components["schemas"]["AgentDetail"];
type MessageDetail = components["schemas"]["MessageDetail"];
type EvalMetricResponse = components["schemas"]["EvalMetricResponse"];

type DrawerTab = "prompt" | "messages" | "verdicts";

interface AgentDrawerProps {
  agent: AgentDetail;
  messages: MessageDetail[];
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
            {agentMessages.map(msg => {
              const chColor = channelColorMap.get(msg.channel_id);
              return (
                <div key={msg.message_id} className="flex gap-2.5 px-5 py-2">
                  <div className="flex w-5 shrink-0 flex-col items-center justify-center">
                    <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                      {msg.turn_number}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex items-baseline gap-1.5">
                      <button
                        className={cn(
                          "cursor-pointer rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed hover:underline",
                          chColor?.bg,
                          chColor?.fg
                        )}
                        onClick={() => onNavigateToChannel(msg.channel_id)}
                      >
                        #{msg.channel_id}
                      </button>
                      <button
                        className="cursor-pointer text-[10px] text-muted-foreground hover:underline"
                        onClick={() => onNavigateToMessage(msg.message_id, msg.channel_id)}
                      >
                        {formatTime(msg.timestamp)}
                      </button>
                    </div>
                    <ProseMarkdown>{msg.text}</ProseMarkdown>
                  </div>
                </div>
              );
            })}
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
