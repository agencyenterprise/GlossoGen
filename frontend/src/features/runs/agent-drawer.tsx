"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Hash, X } from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { AgentInstance } from "./agent-instance";
import type { DisplayEntry } from "./display-entry";
import { EvidenceModal } from "./evidence-modal";
import { formatTime, humanize } from "./format";
import { NotificationDisplay } from "./notification-display";
import { ProseMarkdown } from "./prose-markdown";
import { ToolCallDisplay } from "./tool-call-display";

interface RoundGroup {
  round_number: number;
  entries: DisplayEntry[];
}

function groupByRound(messages: DisplayEntry[]): RoundGroup[] {
  const groups: RoundGroup[] = [];
  for (const msg of messages) {
    const last = groups.at(-1);
    if (last && last.round_number === msg.round_number) {
      last.entries.push(msg);
    } else {
      groups.push({ round_number: msg.round_number, entries: [msg] });
    }
  }
  return groups;
}

type MeasurementResponse = components["schemas"]["MeasurementResponse"];

type DrawerTab = "prompt" | "messages" | "metrics";

interface AgentDrawerProps {
  instance: AgentInstance;
  messages: DisplayEntry[];
  agentColor: AgentColor;
  channelColorMap: Map<string, AgentColor>;
  onClose: () => void;
  onNavigateToMessage: (messageId: string, channelId: string) => void;
  onNavigateToChannel: (channelId: string) => void;
  measurements: MeasurementResponse[] | null;
}

function instanceLabel(instance: AgentInstance): string {
  const start = instance.round_start;
  const end = instance.round_end ?? "…";
  const range = `r${start}-${end}`;
  if (instance.is_latest && instance.generation === 1) {
    return range;
  }
  return `Gen ${instance.generation} · ${range}`;
}

export function AgentDrawer({
  instance,
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
  const instanceMessages = useMemo(
    () =>
      messages.filter(
        m =>
          m.sender_agent_id === instance.agent_id &&
          m.round_number >= instance.round_start &&
          (instance.round_end === null || m.round_number <= instance.round_end)
      ),
    [messages, instance.agent_id, instance.round_start, instance.round_end]
  );
  const roundGroups = useMemo(() => groupByRound(instanceMessages), [instanceMessages]);
  const agentMetrics = (measurements ?? []).flatMap(measurement => {
    const observations = measurement.per_agent.filter(obs => obs.agent_id === instance.agent_id);
    if (observations.length === 0) {
      return [];
    }
    return observations.map(obs => ({ measurement, observation: obs }));
  });
  const showAggregateMetricsCaveat = !instance.is_latest || instance.generation > 1;
  const roundNumbers = useMemo(() => roundGroups.map(g => g.round_number), [roundGroups]);

  // Track which round divider is currently topmost in the scroll viewport so
  // the floating "Round N" badge in the Messages tab reflects what's actually
  // visible rather than the chat-pane's scroll state.
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);
  const roundDividerRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [currentDrawerRound, setCurrentDrawerRound] = useState<number | null>(null);
  const [showRoundJumper, setShowRoundJumper] = useState(false);

  useEffect(() => {
    if (activeTab !== "messages") return;
    const root = messagesScrollRef.current;
    if (!root || roundNumbers.length === 0) return;
    const visibility = new Map<number, number>();
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          const round = Number(entry.target.getAttribute("data-round-number"));
          if (Number.isNaN(round)) continue;
          if (entry.isIntersecting) {
            visibility.set(round, entry.intersectionRatio);
          } else {
            visibility.delete(round);
          }
        }
        if (visibility.size === 0) {
          return;
        }
        const topmost = [...visibility.keys()].sort((a, b) => a - b)[0];
        if (topmost !== undefined) {
          setCurrentDrawerRound(topmost);
        }
      },
      { root, threshold: [0, 0.1, 0.5, 1] }
    );
    for (const node of roundDividerRefs.current.values()) {
      observer.observe(node);
    }
    return () => observer.disconnect();
  }, [activeTab, roundNumbers]);

  // Display round falls back to the first round of this instance when the
  // observer has not yet fired (initial mount, post-tab-switch, or
  // currentDrawerRound now lies outside the round set after a re-render).
  const displayRound =
    currentDrawerRound !== null && roundNumbers.includes(currentDrawerRound)
      ? currentDrawerRound
      : (roundNumbers[0] ?? null);

  const jumpToRound = (roundNumber: number) => {
    const node = roundDividerRefs.current.get(roundNumber);
    if (node) {
      node.scrollIntoView({ behavior: "instant", block: "start" });
    }
    setShowRoundJumper(false);
  };

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
          {deriveInitials(instance.role_name)}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[15px] font-medium">{instance.role_name}</span>
            <span className="rounded-md border border-border bg-muted/50 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              {instanceLabel(instance)}
            </span>
            {instance.is_latest && instance.round_end === null ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:text-emerald-400">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                live
              </span>
            ) : null}
          </div>
          <div className="text-[11px] text-muted-foreground">
            {instance.provider}/{instance.model}
          </div>
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
          Messages ({instanceMessages.length})
        </TabButton>
        {agentMetrics.length > 0 ? (
          <TabButton active={activeTab === "metrics"} onClick={() => setActiveTab("metrics")}>
            Metrics ({agentMetrics.length})
          </TabButton>
        ) : null}
      </div>

      {/* Body */}
      <div
        ref={activeTab === "messages" ? messagesScrollRef : null}
        className="relative flex-1 overflow-y-auto"
      >
        {activeTab === "prompt" ? (
          <div className="p-5">
            <ProseMarkdown className="rounded-lg bg-muted/50 p-3">
              {instance.system_prompt}
            </ProseMarkdown>
          </div>
        ) : null}
        {activeTab === "messages" ? (
          <div className="py-2">
            {displayRound !== null ? (
              <div className="sticky top-2 z-30 flex justify-center">
                <div className="inline-flex items-center gap-1.5">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur">
                    <Hash className="h-3 w-3" />
                    Round {displayRound}
                  </span>
                  {roundNumbers.length > 1 ? (
                    <div className="relative">
                      <Tooltip label="Jump to round">
                        <button
                          type="button"
                          aria-haspopup="listbox"
                          aria-expanded={showRoundJumper}
                          aria-label="Jump to round"
                          onClick={() => setShowRoundJumper(v => !v)}
                          className="inline-flex cursor-pointer items-center justify-center rounded-full border border-border bg-background/90 p-1 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
                        >
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      </Tooltip>
                      {showRoundJumper ? (
                        <div
                          role="listbox"
                          aria-label="Rounds"
                          className="absolute right-0 top-full z-40 mt-1 w-32 overflow-hidden rounded-md border border-border bg-background shadow-lg"
                        >
                          <div className="max-h-64 overflow-y-auto py-1">
                            {roundNumbers.map(n => (
                              <button
                                key={n}
                                type="button"
                                role="option"
                                aria-selected={n === displayRound}
                                onClick={() => jumpToRound(n)}
                                className={cn(
                                  "block w-full px-3 py-1 text-left text-[11px] transition-colors hover:bg-muted",
                                  n === displayRound
                                    ? "font-medium text-foreground"
                                    : "text-muted-foreground"
                                )}
                              >
                                Round {n}
                              </button>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
            {roundGroups.length === 0 ? (
              <div className="px-5 py-8 text-center text-xs text-muted-foreground">
                No messages from this generation yet.
              </div>
            ) : null}
            {roundGroups.map(group => (
              <div key={group.round_number}>
                <div
                  ref={node => {
                    if (node) {
                      roundDividerRefs.current.set(group.round_number, node);
                    } else {
                      roundDividerRefs.current.delete(group.round_number);
                    }
                  }}
                  data-round-number={group.round_number}
                  className="flex items-center gap-2 border-y border-border bg-background/95 px-5 py-1 backdrop-blur"
                >
                  <div className="h-px flex-1 bg-border" />
                  <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    Round {group.round_number}
                  </span>
                  <div className="h-px flex-1 bg-border" />
                </div>
                <div className="space-y-2 px-5 py-3">
                  {group.entries.map(entry => {
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
                            judgeMetadata={entry.judge_metadata}
                            toolMetadata={entry.tool_metadata}
                          />
                        ) : (
                          <ProseMarkdown className={cn(!entry.is_reasoning && "text-foreground")}>
                            {entry.text}
                          </ProseMarkdown>
                        )}
                        <div className="mt-1 text-[10px] text-muted-foreground">
                          {formatTime(entry.timestamp)}
                        </div>
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
            {showAggregateMetricsCaveat ? (
              <div className="pb-2 text-[11px] text-muted-foreground">
                Metrics aggregated across all generations of this agent.
              </div>
            ) : null}
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
