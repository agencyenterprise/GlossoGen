"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  Copy,
  FlaskConical,
  HelpCircle,
  Loader2,
  PanelRightOpen,
  Pencil,
  Radio,
  StickyNote,
  Sword,
  Tag,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import { useEventStream } from "@/shared/lib/use-event-stream";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import { ChatPane } from "./chat-pane";
import { CollapsibleConfigBadges } from "./collapsible-config-badges";
import { EvalVerdictSummary } from "./eval-verdict-summary";
import { mergeEntries } from "./display-entry";
import { LabelBadges } from "./eval-label-group";
import { EvalLogPanel } from "./eval-log-panel";
import { EvalPanel } from "./eval-panel";
import {
  ForkBadge,
  ForkPointFab,
  InternJoinFab,
  InternTakeoverFab,
  SwapPointFab,
} from "./fork-badge";
import { StartEvaluationModal } from "./start-evaluation-modal";
import {
  elapsedSince,
  formatConfigValue,
  formatConfigValueFull,
  formatCost,
  formatDuration,
  humanize,
  sortConfigEntries,
} from "./format";
import { LogPanel } from "./log-panel";
import { RunSidebar } from "./run-sidebar";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { ModelPicker } from "./model-picker";
import { useFork } from "./use-fork";
import { ConfigValueModal } from "./config-value-modal";
import { AgentModelOverrides, type AgentModelOverride } from "./agent-model-overrides";
import { LabelPickerModal } from "./label-picker-modal";
import { NoteEditorModal } from "./note-editor-modal";

function extractModelOverridesFromScenarioConfig(args: {
  scenarioConfig: Record<string, unknown>;
}): Record<string, AgentModelOverride> {
  const rawOverrides = args.scenarioConfig.model_overrides;
  if (typeof rawOverrides !== "object" || rawOverrides === null || Array.isArray(rawOverrides)) {
    return {};
  }

  const overrides: Record<string, AgentModelOverride> = {};
  for (const [agentId, entry] of Object.entries(rawOverrides)) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      continue;
    }
    const payload = entry as Record<string, unknown>;
    const model = payload.model;
    const provider = payload.provider;
    if (typeof model !== "string" || model.trim() === "") {
      continue;
    }
    if (typeof provider !== "string" || provider.trim() === "") {
      continue;
    }
    overrides[agentId] = {
      model: model.trim(),
      provider: provider.trim(),
    };
  }
  return overrides;
}

function deriveInitialForkModelOverrides(args: {
  sourceModel: string;
  sourceProvider: string;
  agents: { agent_id: string; model: string; provider: string }[];
  scenarioConfig: Record<string, unknown>;
}): Record<string, AgentModelOverride> {
  const fromScenarioConfig = extractModelOverridesFromScenarioConfig({
    scenarioConfig: args.scenarioConfig,
  });
  if (Object.keys(fromScenarioConfig).length > 0) {
    return fromScenarioConfig;
  }

  const inferred: Record<string, AgentModelOverride> = {};
  for (const agent of args.agents) {
    const matchesSourceModel = agent.model === args.sourceModel;
    const matchesSourceProvider = agent.provider === args.sourceProvider;
    if (matchesSourceModel && matchesSourceProvider) {
      continue;
    }
    inferred[agent.agent_id] = {
      model: agent.model,
      provider: agent.provider,
    };
  }
  return inferred;
}

export function RunDetail({ scenario, runDirName }: { scenario: string; runDirName: string }) {
  const runId = `${scenario}/${runDirName}`;
  const [configPreview, setConfigPreview] = useState<{ key: string; value: string } | null>(null);
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);
  const [highlightNonce, setHighlightNonce] = useState(0);
  const [showDescription, setShowDescription] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [showEvalLogs, setShowEvalLogs] = useState(false);
  const [showEvalPanel, setShowEvalPanel] = useState(true);
  const [forkModalMessageId, setForkModalMessageId] = useState<string | null>(null);
  const [showEvalModal, setShowEvalModal] = useState(false);
  const [evalJustLaunched, setEvalJustLaunched] = useState(false);
  const [copiedRunId, setCopiedRunId] = useState(false);
  const [showLabelPicker, setShowLabelPicker] = useState(false);
  const [showNoteEditor, setShowNoteEditor] = useState(false);

  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const fork = useFork(runId);

  const handleSelectChannel = useCallback((ch: string | null) => {
    setSelectedChannel(ch);
    setSelectedAgent(null);
    setShowLogs(false);
    setShowEvalLogs(false);
  }, []);

  function handleNavigateToMessage(messageId: string, channelId: string) {
    flushSync(() => {
      setSelectedAgent(null);
      setSelectedChannel(channelId);
      setShowLogs(false);
      setShowEvalLogs(false);
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
      const { data, error } = await api.GET("/api/runs/{scenario}/{run_dir_name}", {
        params: { path: { scenario, run_dir_name: runDirName } },
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
      if (status === "starting") {
        return 2_000;
      }
      if (query.state.data?.evaluation_in_progress || evalJustLaunched) {
        return 5_000;
      }
      return false;
    },
  });

  const stopMutation = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/api/runs/{scenario}/{run_dir_name}/stop", {
        params: { path: { scenario, run_dir_name: runDirName } },
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
  const sseEnabled = restData?.status === "in_progress" || restData?.status === "starting";
  const sse = useEventStream(runId, sseEnabled, knownEventIds, true);

  // When SSE reports simulation ended, refetch REST for evaluation + debug logs
  const sseStatus = sse.status;
  const hasSimEnded =
    sseStatus === "scenario_complete" || sseStatus === "error" || sseStatus === "killed";
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
  const isInProgress = effectiveStatus === "in_progress" || effectiveStatus === "starting";

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

    const seenToolCallIds = new Set(restToolUse.map(t => t.call_id));
    const newToolUse = sse.toolUse.filter(t => !seenToolCallIds.has(t.call_id));

    return mergeEntries(
      [...restMessages, ...newMessages],
      [...restReasoning, ...newReasoning],
      [...restToolUse, ...newToolUse]
    );
  }, [restData, sse.messages, sse.reasoning, sse.toolUse]);

  // Auto-highlight a message from ?highlight= query param (e.g. from branches viewer)
  const highlightParam = searchParams.get("highlight");
  const [didAutoHighlight, setDidAutoHighlight] = useState(false);
  useEffect(() => {
    if (!highlightParam || didAutoHighlight || displayEntries.length === 0) {
      return;
    }
    requestAnimationFrame(() => {
      setDidAutoHighlight(true);
      setHighlightNonce(n => n + 1);
      setHighlightedMessageId(highlightParam);
    });
  }, [highlightParam, didAutoHighlight, displayEntries.length]);

  const channelMessages = displayEntries.filter(
    e => !e.is_reasoning && !e.is_tool_use && !e.is_notification_result
  ).length;
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

  const handleConfirmFork = useCallback(
    (model: string, provider: string, modelOverrides: Record<string, AgentModelOverride>) => {
      if (!forkModalMessageId) return;
      fork.forkMutation.mutate({
        targetMessageId: forkModalMessageId,
        model,
        provider,
        knobs: { model_overrides: modelOverrides },
      });
      setForkModalMessageId(null);
    },
    [forkModalMessageId, fork.forkMutation]
  );

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
  const uniqueModelKeys = [...new Set(allAgents.map(a => `${a.provider}:${a.model}`))];
  let modelLabel: string;
  if (uniqueModelKeys.length === 1) {
    modelLabel = uniqueModelKeys[0] ?? "unknown";
  } else if (uniqueModelKeys.length === 0) {
    modelLabel = "unknown";
  } else {
    modelLabel = `${uniqueModelKeys.length} models`;
  }

  const evaluation = restData.evaluation;
  const evaluationInProgress = restData.evaluation_in_progress || evalJustLaunched;
  const hasLogs = allDebugLogs.length > 0;
  const hasEvalLogs = evaluationInProgress || evaluation !== null || restData.has_eval_log_file;
  const activeAgent = allAgents.find(a => a.agent_id === selectedAgent);
  const activeAgentColor = selectedAgent ? agentColorMap.get(selectedAgent) : undefined;
  const forkEnabled =
    effectiveStatus === "scenario_complete" ||
    effectiveStatus === "error" ||
    effectiveStatus === "killed";

  return (
    <div className="mx-auto flex h-dvh max-w-7xl min-h-0 flex-col px-4 py-4">
      {/* Back link */}
      <Link
        href="/runs"
        className="mb-2 inline-flex shrink-0 items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" /> back to runs
      </Link>

      {/* Header */}
      <div className="mb-3 flex shrink-0 flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-center gap-1.5">
          <h1 className="text-base font-medium">{humanize(restData.scenario_name)}</h1>
          {restData.fork_source ? (
            <ForkBadge
              sourceRunId={restData.fork_source.source_run_id}
              targetMessageId={restData.fork_source.target_message_id}
            />
          ) : null}
          <span className="group/help relative">
            <button
              aria-label="Scenario description"
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => setShowDescription(true)}
            >
              <HelpCircle className="h-4 w-4" />
            </button>
            <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/help:block">
              Scenario description
            </span>
          </span>
          <span className="group/copy relative">
            <button
              aria-label="Copy run ID"
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => {
                navigator.clipboard.writeText(runId);
                setCopiedRunId(true);
                setTimeout(() => setCopiedRunId(false), 2000);
              }}
            >
              {copiedRunId ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </button>
            <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/copy:block">
              {copiedRunId ? "Copied!" : "Copy run ID"}
            </span>
          </span>
        </span>
        <span className="text-[13px] text-muted-foreground">
          {maxRound} rounds · {channelMessages} messages · {timelineEntries} events ·{" "}
          {allAgents.length} agents
          {totalCostUsd > 0 ? <> · {formatCost(totalCostUsd)}</> : null}
          {durationSeconds > 0 ? <> · {formatDuration(durationSeconds)}</> : null}
          {" · "}
          <span className="group relative cursor-default">
            {modelLabel}
            <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-max rounded-md border border-border bg-background px-3 py-2 text-xs shadow-lg group-hover:block">
              {allAgents.map(a => (
                <div key={a.agent_id} className="flex justify-between gap-4 py-0.5">
                  <span className="text-muted-foreground">{a.role_name}</span>
                  <span className="font-mono">
                    {a.provider}:{a.model}
                  </span>
                </div>
              ))}
            </span>
          </span>
          {!isInProgress && !evaluationInProgress && forkEnabled ? (
            <>
              {" · "}
              <span className="group/eval relative">
                <button
                  className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  onClick={() => setShowEvalModal(true)}
                >
                  <FlaskConical className="h-3 w-3" />
                  {evaluation !== null ? "Re-run Eval" : "Run Eval"}
                </button>
                <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/eval:block">
                  {evaluation !== null
                    ? "Re-run LLM-as-judge evaluation"
                    : "Run LLM-as-judge evaluation"}
                </span>
              </span>
            </>
          ) : null}
          {" · "}
          <button
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowLabelPicker(true)}
          >
            <Tag className="h-3 w-3" />
            Labels
          </button>
          {" · "}
          <button
            className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => setShowNoteEditor(true)}
          >
            {restData.note ? <Pencil className="h-3 w-3" /> : <StickyNote className="h-3 w-3" />}
            {restData.note ? "Edit Note" : "Add Note"}
          </button>
        </span>
      </div>

      {/* Scenario config */}
      {restData.scenario_config && Object.keys(restData.scenario_config).length > 0 ? (
        <CollapsibleConfigBadges
          containerClassName="mb-3 shrink-0"
          entries={sortConfigEntries(Object.entries(restData.scenario_config))}
          toggleClassName="inline-flex items-center rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px] text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5"
          renderBadge={([key, value]) => (
            <button
              key={key}
              type="button"
              onClick={() => setConfigPreview({ key, value: formatConfigValueFull(value) })}
              className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-[12px] transition-colors hover:border-primary hover:bg-primary/5"
            >
              <span className="shrink-0 text-muted-foreground">{humanize(key)}</span>
              <span className="max-w-64 truncate font-medium">{formatConfigValue(value)}</span>
            </button>
          )}
        />
      ) : null}

      {/* Eval verdict summary (plain text, separated from labels) */}
      <EvalVerdictSummary labels={restData.labels} size="md" containerClassName="mb-3 shrink-0" />

      {/* Regular labels */}
      {restData.labels.some(label => !label.startsWith("eval:")) ? (
        <div className="mb-3 flex shrink-0 flex-wrap gap-1.5">
          <LabelBadges labels={restData.labels} size="md" />
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
        <div className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-yellow-300/50 bg-yellow-50 px-3 py-1.5 text-xs text-yellow-800 dark:border-yellow-700/50 dark:bg-yellow-950/30 dark:text-yellow-300">
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
          {effectiveStatus !== "starting" ? (
            <span className="group/stop relative ml-auto">
              <button
                className="rounded p-1 transition-colors hover:bg-yellow-200 dark:hover:bg-yellow-800/50"
                aria-label="Stop simulation"
                onClick={() => stopMutation.mutate()}
              >
                <Sword className="h-3 w-3" />
              </button>
              <span className="pointer-events-none absolute left-1/2 top-full z-20 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/stop:block">
                Stop simulation
              </span>
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Evaluation in-progress banner */}
      {!isInProgress && evaluationInProgress ? (
        <div className="mb-2 flex shrink-0 items-center gap-2 rounded-lg border border-blue-300/50 bg-blue-50 px-3 py-1.5 text-xs text-blue-800 dark:border-blue-700/50 dark:bg-blue-950/30 dark:text-blue-300">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Evaluation in progress...</span>
        </div>
      ) : null}

      {/* Shell */}
      <div
        className={cn(
          "relative grid min-h-0 flex-1 rounded-xl border border-border bg-background *:min-h-0",
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
          showEvalLogs={showEvalLogs}
          hasLogs={hasLogs}
          hasEvalLogs={hasEvalLogs}
          agentColorMap={agentColorMap}
          onSelectChannel={handleSelectChannel}
          onSelectAgent={setSelectedAgent}
          onSelectLogs={() => {
            setShowLogs(true);
            setShowEvalLogs(false);
            setSelectedAgent(null);
          }}
          onSelectEvalLogs={() => {
            setShowEvalLogs(true);
            setShowLogs(false);
            setSelectedAgent(null);
          }}
        />

        {/* Main content: chat, logs, or eval logs */}
        {showLogs ? (
          <LogPanel logs={allDebugLogs} />
        ) : showEvalLogs ? (
          <EvalLogPanel runId={runId} evaluationInProgress={evaluationInProgress} />
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
            onForkFromMessage={handleForkFromMessage}
            forkPointMessageId={restData.fork_source?.target_message_id ?? null}
            swapRoundNumber={restData.swap_point?.round_number ?? null}
            swappedObserverDisplayNames={restData.swap_point?.swapped_observer_display_names ?? []}
            internJoinRoundNumber={restData.intern_join?.round_number ?? null}
            internTakeoverRoundNumber={restData.intern_takeover?.round_number ?? null}
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

      {/* Start evaluation modal */}
      {showEvalModal ? (
        <StartEvaluationModal
          runId={runId}
          scenarioName={restData.scenario_name}
          onClose={() => setShowEvalModal(false)}
          onLaunched={() => {
            setEvalJustLaunched(true);
            setTimeout(() => setEvalJustLaunched(false), 30_000);
          }}
        />
      ) : null}

      {showLabelPicker ? (
        <LabelPickerModal
          runId={runId}
          currentLabels={restData.labels}
          onClose={() => setShowLabelPicker(false)}
        />
      ) : null}

      {showNoteEditor ? (
        <NoteEditorModal
          runId={runId}
          initialContent={restData.note ?? null}
          onClose={() => setShowNoteEditor(false)}
        />
      ) : null}

      {/* Fork confirmation modal */}
      {forkModalMessageId ? (
        <ForkModal
          isPending={fork.forkMutation.isPending}
          sourceModel={restData.agents[0]?.model ?? ""}
          sourceProvider={restData.agents[0]?.provider ?? restData.provider}
          sourceAgents={restData.agents.map(agent => ({
            agent_id: agent.agent_id,
            role_name: agent.role_name,
            model: agent.model,
            provider: agent.provider,
          }))}
          initialModelOverrides={deriveInitialForkModelOverrides({
            sourceModel: restData.agents[0]?.model ?? "",
            sourceProvider: restData.agents[0]?.provider ?? restData.provider,
            agents: restData.agents.map(agent => ({
              agent_id: agent.agent_id,
              model: agent.model,
              provider: agent.provider,
            })),
            scenarioConfig: restData.scenario_config,
          })}
          onConfirm={handleConfirmFork}
          onCancel={() => setForkModalMessageId(null)}
        />
      ) : null}

      {configPreview ? (
        <ConfigValueModal
          configKey={configPreview.key}
          value={configPreview.value}
          onClose={() => setConfigPreview(null)}
          secondaryAction={null}
        />
      ) : null}

      {(() => {
        let nextStackIndex = 0;
        const forkStackIndex = restData.fork_source !== null ? nextStackIndex++ : null;
        const swapStackIndex = restData.swap_point !== null ? nextStackIndex++ : null;
        const internJoinStackIndex = restData.intern_join !== null ? nextStackIndex++ : null;
        const internTakeoverStackIndex =
          restData.intern_takeover !== null ? nextStackIndex++ : null;

        const scrollToDivider = (elementId: string) => {
          flushSync(() => {
            setSelectedAgent(null);
            setShowLogs(false);
            setSelectedChannel(null);
            setHighlightedMessageId(null);
          });
          requestAnimationFrame(() => {
            const el = document.getElementById(elementId);
            if (!el) return;
            el.scrollIntoView({ behavior: "smooth", block: "center" });
            el.classList.add("animate-highlight");
            setTimeout(() => {
              el.classList.remove("animate-highlight");
            }, 1500);
          });
        };

        return (
          <>
            {restData.fork_source && forkStackIndex !== null ? (
              <ForkPointFab
                stackIndex={forkStackIndex}
                onClick={() => {
                  const forkMsgId = restData.fork_source?.target_message_id;
                  if (!forkMsgId) return;
                  const entry = displayEntries.find(e => e.message_id === forkMsgId);
                  if (!entry) return;

                  const messageChannel = entry.channel_id;
                  const needsChannelSwitch =
                    selectedChannel !== null && selectedChannel !== messageChannel;

                  flushSync(() => {
                    setSelectedAgent(null);
                    setShowLogs(false);
                    if (needsChannelSwitch) {
                      setSelectedChannel(null);
                    }
                    setHighlightedMessageId(null);
                  });
                  setHighlightNonce(n => n + 1);
                  setHighlightedMessageId(forkMsgId);
                }}
              />
            ) : null}

            {restData.swap_point && swapStackIndex !== null ? (
              <SwapPointFab
                stackIndex={swapStackIndex}
                roundNumber={restData.swap_point.round_number}
                onClick={() => scrollToDivider("swap-divider")}
              />
            ) : null}

            {restData.intern_join && internJoinStackIndex !== null ? (
              <InternJoinFab
                stackIndex={internJoinStackIndex}
                roundNumber={restData.intern_join.round_number}
                onClick={() => scrollToDivider("intern-join-divider")}
              />
            ) : null}

            {restData.intern_takeover && internTakeoverStackIndex !== null ? (
              <InternTakeoverFab
                stackIndex={internTakeoverStackIndex}
                roundNumber={restData.intern_takeover.round_number}
                onClick={() => scrollToDivider("intern-takeover-divider")}
              />
            ) : null}
          </>
        );
      })()}
    </div>
  );
}

function ForkModal({
  isPending,
  sourceModel,
  sourceProvider,
  sourceAgents,
  initialModelOverrides,
  onConfirm,
  onCancel,
}: {
  isPending: boolean;
  sourceModel: string;
  sourceProvider: string;
  sourceAgents: { agent_id: string; role_name: string; model: string; provider: string }[];
  initialModelOverrides: Record<string, AgentModelOverride>;
  onConfirm: (
    model: string,
    provider: string,
    modelOverrides: Record<string, AgentModelOverride>
  ) => void;
  onCancel: () => void;
}) {
  const [model, setModel] = useState(sourceModel);
  const [provider, setProvider] = useState(sourceProvider);
  const [modelOverrides, setModelOverrides] =
    useState<Record<string, AgentModelOverride>>(initialModelOverrides);

  const { data } = useQuery({
    queryKey: ["scenarios"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/scenarios");
      if (error) {
        throw new Error("Failed to fetch scenarios");
      }
      return data;
    },
  });

  function handleModelSelect(selectedModel: string, selectedProvider: string) {
    setModel(selectedModel);
    setProvider(selectedProvider);
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/40 px-4 py-4">
      <div className="flex min-h-full items-center justify-center">
        <div className="flex w-full max-w-md max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-xl">
          <div className="min-h-0 flex-1 overflow-y-auto p-5">
            <h3 className="mb-3 text-sm font-medium">Fork simulation</h3>
            <p className="mb-3 text-xs text-muted-foreground">
              A new simulation will start from the edited message with the channel history up to
              that point.
            </p>

            <div className="mb-4">
              <ModelPicker
                label="Model"
                models={data?.models ?? []}
                selectedModel={model}
                onSelect={handleModelSelect}
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium">Agent Model Overrides</label>
              <p className="text-xs text-muted-foreground">
                Overrides from this run are pre-selected. You can adjust any agent before launching.
              </p>
              <AgentModelOverrides
                agents={sourceAgents}
                models={data?.models ?? []}
                overrides={modelOverrides}
                onChange={setModelOverrides}
              />
            </div>
          </div>

          <div className="flex shrink-0 justify-end gap-2 border-t border-border px-5 py-3">
            <button
              className="rounded-md border border-border px-3 py-1 text-[12px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={onCancel}
              disabled={isPending}
            >
              Cancel
            </button>
            <button
              className="rounded-md bg-foreground px-3 py-1 text-[12px] font-medium text-background transition-opacity hover:opacity-80 disabled:opacity-50"
              onClick={() => onConfirm(model, provider, modelOverrides)}
              disabled={isPending || !model}
            >
              {isPending ? "Launching..." : "Launch fork"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
