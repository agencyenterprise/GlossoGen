"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  HelpCircle,
  Loader2,
  PanelRightOpen,
  Radio,
  Sword,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { useEventStream } from "@/shared/lib/use-event-stream";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { ChatPane } from "./chat-pane";
import { mergeEntries } from "./display-entry";
import { EvalPanel } from "./eval-panel";
import { ForkBadge } from "./fork-badge";
import { elapsedSince, formatConfigValue, formatCost, formatDuration, humanize } from "./format";
import { LogPanel } from "./log-panel";
import { RunSidebar } from "./run-sidebar";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { useFork } from "./use-fork";

export function RunDetail({ runId }: { runId: string }) {
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [showEvalPanel, setShowEvalPanel] = useState(true);
  const [forkModalMessageId, setForkModalMessageId] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const fork = useFork(runId);

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

  // REST fetch — polls every 10s while in-progress to keep cost/messages current
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
    refetchInterval: query => {
      const status = query.state.data?.status;
      if (status === "in_progress") {
        return 10_000;
      }
      return false;
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/runs/{run_id}/stop", {
        params: { path: { run_id: runId } },
      });
      if (error) {
        throw new Error("Failed to stop simulation");
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
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

  // SSE streaming for in-progress runs
  const sseEnabled = restData?.status === "in_progress";
  const sse = useEventStream(runId, sseEnabled, knownEventIds);

  // When SSE reports simulation ended, refetch REST for evaluation + debug logs
  const sseStatus = sse.status;
  const hasSimEnded = sseStatus === "scenario_complete" || sseStatus === "error";
  useEffect(() => {
    if (hasSimEnded) {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
    }
  }, [hasSimEnded, queryClient, runId]);

  // If SSE was enabled (REST said in_progress) but failed to connect,
  // the simulation likely ended between the REST fetch and SSE attempt.
  // Refetch REST to get the updated status.
  const sseFailedToConnect = sseEnabled && !sse.isConnected && sseStatus === null;
  useEffect(() => {
    if (!sseFailedToConnect) return undefined;
    const timer = setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
    }, 2000);
    return () => clearTimeout(timer);
  }, [sseFailedToConnect, queryClient, runId]);

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
    const restToolUse = restData?.tool_use ?? [];

    // Dedup messages by message_id (REST and SSE may overlap)
    const seenMessageIds = new Set(restMessages.map(m => m.message_id));
    const newMessages = sse.messages.filter(m => !seenMessageIds.has(m.message_id));

    const seenReasoningIds = new Set(restReasoning.map(r => r.message_id));
    const newReasoning = sse.reasoning.filter(r => !seenReasoningIds.has(r.message_id));

    const seenToolUseIds = new Set(restToolUse.map(t => t.message_id));
    const newToolUse = sse.toolUse.filter(t => !seenToolUseIds.has(t.message_id));

    return mergeEntries(
      [...restMessages, ...newMessages],
      [...restReasoning, ...newReasoning],
      [...restToolUse, ...newToolUse]
    );
  }, [restData, sse.messages, sse.reasoning, sse.toolUse]);

  const channelMessages = displayEntries.filter(e => !e.is_reasoning && !e.is_tool_use).length;
  const timelineEntries = displayEntries.length;
  const restCost = restData?.total_cost_usd ?? 0;
  const totalCostUsd = Math.max(sse.totalCostUsd, restCost);
  const durationSeconds =
    sse.durationSeconds > 0 ? sse.durationSeconds : (restData?.duration_seconds ?? 0);

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

  const handleForkFromMessage = useCallback((targetMessageId: string) => {
    setForkModalMessageId(targetMessageId);
  }, []);

  const handleConfirmFork = useCallback(() => {
    if (!forkModalMessageId) return;
    fork.forkMutation.mutate({
      targetMessageId: forkModalMessageId,
    });
    setForkModalMessageId(null);
  }, [forkModalMessageId, fork.forkMutation]);

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

  const maxRound = displayEntries.reduce((max, m) => Math.max(max, m.round_number), 0);
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
  const forkEnabled = effectiveStatus === "scenario_complete" || effectiveStatus === "error";

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
          {restData.fork_source ? (
            <ForkBadge
              sourceRunId={restData.fork_source.source_run_id}
              targetMessageId={restData.fork_source.target_message_id}
            />
          ) : null}
          <button
            aria-label="Scenario description"
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowDescription(true)}
          >
            <HelpCircle className="h-4 w-4" />
          </button>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {maxRound} rounds · {channelMessages} messages · {timelineEntries} events ·{" "}
          {allAgents.length} agents
          {totalCostUsd > 0 ? <> · {formatCost(totalCostUsd)}</> : null}
          {durationSeconds > 0 ? <> · {formatDuration(durationSeconds)}</> : null}
          {" · "}
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
          {Object.entries(restData.scenario_config).map(([key, value]) => (
            <span
              key={key}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px]"
            >
              <span className="text-muted-foreground">{humanize(key)}</span>
              <span className="font-medium">{formatConfigValue(value)}</span>
            </span>
          ))}
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
            {restData ? <> · {formatDuration(elapsedSince(restData.timestamp))}</> : null}
          </span>
          <button
            className="ml-auto rounded p-1 transition-colors hover:bg-yellow-200 dark:hover:bg-yellow-800/50"
            aria-label="Stop simulation"
            onClick={() => stopMutation.mutate()}
          >
            <Sword className="h-3 w-3" />
          </button>
        </div>
      ) : null}

      {/* Shell */}
      <div
        className={cn(
          "relative grid h-[calc(100vh-120px)] min-h-[500px] overflow-hidden rounded-xl border border-border bg-background",
          evaluation !== null && showEvalPanel
            ? "grid-cols-[192px_1fr_280px]"
            : "grid-cols-[192px_1fr]"
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
            runId={runId}
            messages={displayEntries}
            agents={allAgents}
            selectedChannel={selectedChannel}
            agentColorMap={agentColorMap}
            channelColorMap={channelColorMap}
            onSelectAgent={setSelectedAgent}
            highlightedMessageId={highlightedMessageId}
            highlightNonce={highlightNonce}
            forkEnabled={forkEnabled}
            editingMessageId={fork.editingMessageId}
            pendingEdits={fork.pendingEdits}
            onStartEdit={fork.startEdit}
            onSaveEdit={fork.saveEdit}
            onCancelEdit={fork.cancelEdit}
            onRemoveEdit={fork.removeEdit}
            onForkFromMessage={handleForkFromMessage}
          />
        )}

        {/* Right panel: eval (completed) */}
        {!isInProgress && evaluation !== null && showEvalPanel ? (
          <EvalPanel evaluation={evaluation} onClose={() => setShowEvalPanel(false)} />
        ) : null}

        {/* Right panel toggle (when hidden) */}
        {!isInProgress && evaluation !== null && !showEvalPanel ? (
          <button
            className="absolute right-2 top-12 z-10 rounded-md border border-border bg-background p-1.5 text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowEvalPanel(true)}
            title="Show evaluators panel"
          >
            <PanelRightOpen className="h-4 w-4" />
          </button>
        ) : null}

        {/* Agent drawer */}
        {activeAgent && activeAgentColor ? (
          <AgentDrawer
            agent={activeAgent}
            messages={displayEntries}
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

      {/* Fork confirmation modal */}
      {forkModalMessageId ? (
        <ForkModal
          isPending={fork.forkMutation.isPending}
          onConfirm={handleConfirmFork}
          onCancel={() => setForkModalMessageId(null)}
        />
      ) : null}
    </div>
  );
}

function ForkModal({
  isPending,
  onConfirm,
  onCancel,
}: {
  isPending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-xl border border-border bg-background p-5 shadow-xl">
        <h3 className="mb-3 text-sm font-medium">Fork simulation</h3>
        <p className="mb-4 text-xs text-muted-foreground">
          A new simulation will start from the edited message with the channel history up to that
          point. The same model and provider from the source run will be used.
        </p>
        <div className="flex justify-end gap-2">
          <button
            className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={onCancel}
            disabled={isPending}
          >
            Cancel
          </button>
          <button
            className="rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? "Launching..." : "Launch fork"}
          </button>
        </div>
      </div>
    </div>
  );
}
