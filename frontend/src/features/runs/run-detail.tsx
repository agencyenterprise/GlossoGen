"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, HelpCircle, Loader2, Radio, XCircle } from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { useEventStream } from "@/shared/lib/use-event-stream";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { ChatPane } from "./chat-pane";
import type { DisplayEntry } from "./display-entry";
import { mergeEntries } from "./display-entry";
import { EvalPanel } from "./eval-panel";
import { humanize } from "./format";
import { LogPanel } from "./log-panel";
import { RunSidebar } from "./run-sidebar";
import { ScenarioDescriptionModal } from "./scenario-description-modal";

export function RunDetail({ runId }: { runId: string }) {
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  const queryClient = useQueryClient();

  const handleSelectChannel = useCallback((ch: string | null) => {
    setSelectedChannel(ch);
    setSelectedAgent(null);
    setShowLogs(false);
  }, []);

  function handleNavigateToMessage(messageId: string, channelId: string) {
    flushSync(() => {
      setSelectedAgent(null);
      setSelectedChannel(channelId);
      setShowLogs(false);
      setHighlightedMessageId(null);
    });
    setHighlightNonce(n => n + 1);
    setHighlightedMessageId(messageId);
  }

  // Initial REST fetch — no polling, just a one-time load (+ refetch on SSE completion)
  const {
    data: restData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["run", runId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/runs/{run_id}", {
        params: { path: { run_id: runId } },
      });
      if (error) {
        throw new Error("Failed to fetch run detail");
      }
      return data;
    },
  });

  // Collect known event IDs from the REST snapshot for SSE deduplication
  const knownEventIds = useMemo(() => {
    if (!restData) return new Set<string>();
    const ids = new Set<string>();
    for (const m of restData.messages) {
      ids.add(m.message_id);
    }
    for (const r of restData.reasoning) {
      ids.add(r.message_id);
    }
    return ids;
  }, [restData]);

  // Derive latest turn/round per agent from REST data to seed the SSE hook
  const initialAgentTurns = useMemo(() => {
    if (!restData) return new Map<string, number>();
    const map = new Map<string, number>();
    for (const m of restData.messages) {
      const prev = map.get(m.sender_agent_id) ?? 0;
      if (m.turn_number > prev) {
        map.set(m.sender_agent_id, m.turn_number);
      }
    }
    return map;
  }, [restData]);

  const initialAgentRounds = useMemo(() => {
    if (!restData) return new Map<string, number>();
    const map = new Map<string, number>();
    for (const m of restData.messages) {
      const prev = map.get(m.sender_agent_id) ?? 0;
      if (m.round_number > prev) {
        map.set(m.sender_agent_id, m.round_number);
      }
    }
    return map;
  }, [restData]);

  // SSE streaming for in-progress runs
  const sseEnabled = restData?.status === "in_progress";
  const initialMessageCount = restData?.messages.length ?? 0;
  const sse = useEventStream(
    runId,
    sseEnabled,
    knownEventIds,
    initialAgentTurns,
    initialAgentRounds,
    initialMessageCount
  );

  // When SSE reports simulation ended, refetch REST for evaluation + debug logs
  const sseStatus = sse.status;
  const hasSimEnded = sseStatus === "scenario_complete" || sseStatus === "error";
  useEffect(() => {
    if (hasSimEnded) {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
    }
  }, [hasSimEnded, queryClient, runId]);

  // Determine effective status: SSE overrides REST when streaming
  const effectiveStatus = sseStatus ?? restData?.status ?? null;
  const isInProgress = effectiveStatus === "in_progress";

  // Merge REST + SSE agents (SSE agents are deduplicated by agent_id)
  const allAgents = useMemo(() => {
    if (!restData) return sse.agents;
    const restAgents = restData.agents;
    if (sse.agents.length === 0) return restAgents;
    const seen = new Set(restAgents.map(a => a.agent_id));
    const extra = sse.agents.filter(a => !seen.has(a.agent_id));
    return [...restAgents, ...extra];
  }, [restData, sse.agents]);

  // Merge REST + SSE channel IDs
  const allChannelIds = useMemo(() => {
    const restChannels = restData?.channel_ids ?? [];
    if (sse.channelIds.length === 0) return restChannels;
    const set = new Set([...restChannels, ...sse.channelIds]);
    return [...set];
  }, [restData, sse.channelIds]);

  // Merge REST + SSE messages and reasoning, deduplicating by message_id
  const displayEntries = useMemo(() => {
    const restMessages = restData?.messages ?? [];
    const restReasoning = restData?.reasoning ?? [];

    // Dedup messages by message_id (REST and SSE may overlap)
    const seenMessageIds = new Set(restMessages.map(m => m.message_id));
    const newMessages = sse.messages.filter(m => !seenMessageIds.has(m.message_id));

    const seenReasoningIds = new Set(restReasoning.map(r => r.message_id));
    const newReasoning = sse.reasoning.filter(r => !seenReasoningIds.has(r.message_id));

    return mergeEntries([...restMessages, ...newMessages], [...restReasoning, ...newReasoning]);
  }, [restData, sse.messages, sse.reasoning]);

  // Build partial streaming entries for reasoning text and message previews
  const partialEntries: DisplayEntry[] = useMemo(() => {
    const entries: DisplayEntry[] = [];

    // Reasoning text streaming
    if (sse.streamingAgentId) {
      const text = sse.partialText.get(sse.streamingAgentId);
      if (text) {
        entries.push({
          message_id: `partial-reasoning-${sse.streamingAgentId}`,
          channel_id: "",
          channel_ids: [],
          sender_agent_id: sse.streamingAgentId,
          text,
          timestamp: new Date().toISOString(),
          turn_number: sse.agentTurns.get(sse.streamingAgentId) ?? 0,
          round_number: sse.agentRounds.get(sse.streamingAgentId) ?? 0,
          is_reasoning: true,
          is_partial: true,
        });
      }
    }

    // Message preview streaming (send_message tool calls)
    for (const [agentId, pm] of sse.partialMessages) {
      entries.push({
        message_id: `partial-msg-${agentId}`,
        channel_id: pm.channelId,
        channel_ids: [pm.channelId],
        sender_agent_id: agentId,
        text: pm.text,
        timestamp: new Date().toISOString(),
        turn_number: sse.agentTurns.get(agentId) ?? 0,
        round_number: sse.agentRounds.get(agentId) ?? 0,
        is_reasoning: false,
        is_partial: true,
      });
    }

    return entries;
  }, [sse.streamingAgentId, sse.partialText, sse.partialMessages, sse.agentTurns, sse.agentRounds]);

  const allDisplayEntries = useMemo(
    () => [...displayEntries, ...partialEntries],
    [displayEntries, partialEntries]
  );

  const totalTurns = sse.totalTurns > 0 ? sse.totalTurns : (restData?.total_turns ?? 0);
  const totalMessages = sse.totalMessages > 0 ? sse.totalMessages : (restData?.total_messages ?? 0);

  const agentColorMap = useMemo(
    () => buildAgentColorMap(allAgents.map(a => a.agent_id)),
    [allAgents]
  );
  const channelColorMap = useMemo(() => buildChannelColorMap(allChannelIds), [allChannelIds]);

  const allDebugLogs = useMemo(() => {
    const restLogs = restData?.debug_logs ?? [];
    if (sse.debugLogs.length === 0) return restLogs;
    const seen = new Set(restLogs.map(l => `${l.timestamp}|${l.message}`));
    const newLogs = sse.debugLogs.filter(l => !seen.has(`${l.timestamp}|${l.message}`));
    return [...restLogs, ...newLogs];
  }, [restData?.debug_logs, sse.debugLogs]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !restData) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-destructive">
        <XCircle className="h-8 w-8" />
        <p>Failed to load run</p>
      </div>
    );
  }

  const maxRound = allDisplayEntries.reduce((max, m) => Math.max(max, m.round_number), 0);
  const uniqueModels = [...new Set(allAgents.map(a => a.model))];
  let modelLabel: string;
  if (uniqueModels.length === 1) {
    modelLabel = uniqueModels[0] ?? "unknown";
  } else if (uniqueModels.length === 0) {
    modelLabel = "unknown";
  } else {
    modelLabel = `${uniqueModels.length} models`;
  }

  const evaluation = restData.evaluation;
  const hasLogs = allDebugLogs.length > 0;
  const activeAgent = allAgents.find(a => a.agent_id === selectedAgent);
  const activeAgentColor = selectedAgent ? agentColorMap.get(selectedAgent) : undefined;

  return (
    <div className="mx-auto max-w-7xl px-4 py-4">
      {/* Back link */}
      <Link
        href="/runs"
        className="mb-2 inline-flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> back to runs
      </Link>

      {/* Header */}
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <h1 className="text-base font-medium">{humanize(restData.scenario_name)}</h1>
          <button
            aria-label="Scenario description"
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowDescription(true)}
          >
            <HelpCircle className="h-4 w-4" />
          </button>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {maxRound} rounds · {totalMessages} messages · {totalTurns} turns · {allAgents.length}{" "}
          agents ·{" "}
          {uniqueModels.length <= 1 ? (
            modelLabel
          ) : (
            <span className="group relative cursor-default">
              {modelLabel}
              <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-max rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg group-hover:block">
                {allAgents.map(a => (
                  <div key={a.agent_id} className="flex justify-between gap-4 py-0.5">
                    <span className="text-muted-foreground">{humanize(a.agent_id)}</span>
                    <span className="font-mono">{a.model}</span>
                  </div>
                ))}
              </span>
            </span>
          )}
        </span>
      </div>

      {/* Scenario config */}
      {restData.scenario_config && Object.keys(restData.scenario_config).length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {Object.entries(restData.scenario_config).map(([key, value]) => {
            const display =
              typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
            return (
              <span
                key={key}
                className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px]"
              >
                <span className="text-muted-foreground">{humanize(key)}</span>
                <span className="font-medium">{display}</span>
              </span>
            );
          })}
        </div>
      ) : null}

      {showDescription ? (
        <ScenarioDescriptionModal
          scenarioName={humanize(restData.scenario_name)}
          description={restData.scenario_description}
          onClose={() => setShowDescription(false)}
        />
      ) : null}

      {/* Live streaming banner */}
      {isInProgress ? (
        <div className="mb-2 flex items-center gap-2 rounded-lg border border-yellow-300/50 bg-yellow-50 px-3 py-1.5 text-xs text-yellow-800 dark:border-yellow-700/50 dark:bg-yellow-950/30 dark:text-yellow-300">
          {sse.isConnected ? (
            <Radio className="h-3 w-3 text-green-600 dark:text-green-400" />
          ) : (
            <Loader2 className="h-3 w-3 animate-spin" />
          )}
          <span>
            Simulation in progress
            {sse.isConnected ? " — streaming live" : " — connecting..."}
          </span>
        </div>
      ) : null}

      {/* Shell */}
      <div
        className={cn(
          "relative grid h-[calc(100vh-120px)] min-h-[500px] overflow-hidden rounded-xl border border-border bg-background",
          evaluation !== null ? "grid-cols-[192px_1fr_280px]" : "grid-cols-[192px_1fr]"
        )}
      >
        <RunSidebar
          channelIds={allChannelIds}
          agents={allAgents}
          selectedChannel={selectedChannel}
          selectedAgent={selectedAgent}
          showLogs={showLogs}
          hasLogs={hasLogs}
          agentColorMap={agentColorMap}
          onSelectChannel={handleSelectChannel}
          onSelectAgent={setSelectedAgent}
          onSelectLogs={() => {
            setShowLogs(true);
            setSelectedAgent(null);
          }}
        />

        {/* Main content: chat or logs */}
        {showLogs ? (
          <LogPanel logs={allDebugLogs} />
        ) : (
          <ChatPane
            messages={allDisplayEntries}
            agents={allAgents}
            selectedChannel={selectedChannel}
            agentColorMap={agentColorMap}
            channelColorMap={channelColorMap}
            onSelectAgent={setSelectedAgent}
            highlightedMessageId={highlightedMessageId}
            highlightNonce={highlightNonce}
            streamingAgentId={sse.streamingAgentId}
          />
        )}

        {/* Eval panel */}
        {evaluation !== null ? <EvalPanel evaluation={evaluation} /> : null}

        {/* Agent drawer */}
        {activeAgent && activeAgentColor ? (
          <AgentDrawer
            agent={activeAgent}
            messages={allDisplayEntries}
            agentColor={activeAgentColor}
            channelColorMap={channelColorMap}
            onClose={() => setSelectedAgent(null)}
            onNavigateToMessage={handleNavigateToMessage}
            onNavigateToChannel={channelId => {
              setSelectedAgent(null);
              setSelectedChannel(channelId);
            }}
            evalMetrics={restData.evaluation?.metrics ?? null}
          />
        ) : null}
      </div>
    </div>
  );
}
