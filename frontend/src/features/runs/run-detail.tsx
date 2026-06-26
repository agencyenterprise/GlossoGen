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
import { useGroupPath } from "@/features/auth/group-context";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { AgentDrawer } from "./agent-drawer";
import {
  deriveAgentInstances,
  resolveSelectedInstance,
  type AgentInstance,
} from "./agent-instance";
import { ChatPane, type AgentSwapDivider } from "./chat-pane";
import { CollapsibleConfigBadges } from "./collapsible-config-badges";
import { mergeEntries } from "./display-entry";
import { LabelBadges } from "./eval-label-group";
import { EvalLogPanel } from "./eval-log-panel";
import { EvalPanel } from "./eval-panel";
import {
  AgentSwapPointFab,
  CrossRunReplaceAgentPointFab,
  ForkBadge,
  ForkPointFab,
  InternJoinFab,
  InternTakeoverFab,
  ReplaceAgentPointFab,
  SwapPointFab,
} from "./fork-badge";
import { StartEvaluationModal } from "./start-evaluation-modal";
import {
  elapsedSince,
  formatConfigValue,
  formatConfigValueFull,
  formatCost,
  formatDayHeader,
  formatDuration,
  humanize,
  sortConfigEntries,
} from "./format";
import { LogPanel } from "./log-panel";
import { RunSidebar } from "./run-sidebar";
import { ScenarioDescriptionModal } from "./scenario-description-modal";
import { ReplaceAgentBadge } from "./replace-agent-badge";
import { CrossRunReplaceAgentBadge } from "./cross-run-replace-agent-badge";
import { ResumeAtRoundBadge } from "./resume-at-round-badge";
import { DerivedRunsSection } from "./derived-runs-section";
import { ConfigValueModal } from "./config-value-modal";
import { LabelPickerModal } from "./label-picker-modal";
import { NoteEditorModal } from "./note-editor-modal";

export function RunDetail({ scenario, runDirName }: { scenario: string; runDirName: string }) {
  const groupPath = useGroupPath();
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
  const [showEvalModal, setShowEvalModal] = useState(false);
  const [evalJustLaunched, setEvalJustLaunched] = useState(false);
  const [copiedRunId, setCopiedRunId] = useState(false);
  const [showLabelPicker, setShowLabelPicker] = useState(false);
  const [showNoteEditor, setShowNoteEditor] = useState(false);

  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

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
      const { data, error } = await api.GET("/api/g/{group_slug}/runs/{scenario}/{run_dir_name}", {
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
      const { error } = await api.POST("/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/stop", {
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

  // When SSE reports simulation ended, refetch REST for evaluation status
  const sseStatus = sse.status;
  const hasSimEnded =
    sseStatus === "scenario_complete" || sseStatus === "error" || sseStatus === "killed";
  useEffect(() => {
    if (hasSimEnded) {
      queryClient.invalidateQueries({ queryKey: ["run", runId] });
      queryClient.invalidateQueries({ queryKey: ["run-debug-logs", runId] });
    }
  }, [hasSimEnded, queryClient, runId]);

  // Debug logs fetched separately to keep the main response small
  const { data: debugLogsData } = useQuery({
    queryKey: ["run-debug-logs", runId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/debug-logs",
        {
          params: { path: { scenario, run_dir_name: runDirName } },
        }
      );
      if (error) {
        throw new Error("Failed to fetch debug logs");
      }
      return data;
    },
    refetchInterval: false,
  });

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

  const swapEvents = useMemo(
    () => restData?.agent_swap_events ?? [],
    [restData?.agent_swap_events]
  );

  const observedMaxRound = useMemo(() => {
    let max = 0;
    for (const m of restData?.messages ?? []) {
      if (m.round_number > max) max = m.round_number;
    }
    for (const m of sse.messages) {
      if (m.round_number > max) max = m.round_number;
    }
    return max > 0 ? max : null;
  }, [restData?.messages, sse.messages]);

  const agentInstances = useMemo<AgentInstance[]>(
    () => deriveAgentInstances(allAgents, swapEvents, observedMaxRound, isInProgress),
    [allAgents, swapEvents, observedMaxRound, isInProgress]
  );

  const agentSwapDividers = useMemo(() => {
    const previousModelByAgent = new Map<string, string>();
    for (const a of allAgents) {
      previousModelByAgent.set(a.agent_id, a.model);
    }
    const dividers: AgentSwapDivider[] = [];
    const sorted = [...swapEvents].sort((a, b) => {
      if (a.round_number !== b.round_number) return a.round_number - b.round_number;
      return a.agent_id.localeCompare(b.agent_id);
    });
    const generationsByAgent = new Map<string, number>();
    for (const event of sorted) {
      const previousGeneration = generationsByAgent.get(event.agent_id) ?? 1;
      const generation = previousGeneration + 1;
      generationsByAgent.set(event.agent_id, generation);
      const oldModel = previousModelByAgent.get(event.agent_id) ?? "?";
      const role = allAgents.find(a => a.agent_id === event.agent_id)?.role_name ?? event.agent_id;
      dividers.push({
        agent_id: event.agent_id,
        role_name: role,
        round_number: event.round_number,
        generation,
        old_model: oldModel,
        new_model: event.new_model,
        post_swap_instance_key: `${event.agent_id}:${generation}`,
      });
      previousModelByAgent.set(event.agent_id, event.new_model);
    }
    return dividers;
  }, [allAgents, swapEvents]);

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
    const restRunCycleFailures = restData?.run_cycle_failures ?? [];

    // Dedup messages by message_id (REST and SSE may overlap)
    const seenMessageIds = new Set(restMessages.map(m => m.message_id));
    const newMessages = sse.messages.filter(m => !seenMessageIds.has(m.message_id));

    const seenReasoningIds = new Set(restReasoning.map(r => r.message_id));
    const newReasoning = sse.reasoning.filter(r => !seenReasoningIds.has(r.message_id));

    const seenToolCallIds = new Set(restToolUse.map(t => t.call_id));
    const newToolUse = sse.toolUse.filter(t => !seenToolCallIds.has(t.call_id));

    const seenFailureIds = new Set(restRunCycleFailures.map(f => f.message_id));
    const newFailures = sse.runCycleFailures.filter(f => !seenFailureIds.has(f.message_id));

    const scenarioExtras = restData?.scenario_extras ?? null;
    const restStabilizeMetadata =
      scenarioExtras !== null && scenarioExtras.scenario_name === "veyru"
        ? scenarioExtras.stabilize_metadata_by_call_id
        : {};
    const stabilizeMetadataByCallId = {
      ...restStabilizeMetadata,
      ...sse.stabilizeMetadataByCallId,
    };
    const moveMetadataByCallId =
      scenarioExtras !== null && scenarioExtras.scenario_name === "container_yard_stacking"
        ? scenarioExtras.move_metadata_by_call_id
        : {};

    return mergeEntries(
      [...restMessages, ...newMessages],
      [...restReasoning, ...newReasoning],
      [...restToolUse, ...newToolUse],
      [...restRunCycleFailures, ...newFailures],
      stabilizeMetadataByCallId,
      moveMetadataByCallId
    );
  }, [
    restData,
    sse.messages,
    sse.reasoning,
    sse.toolUse,
    sse.runCycleFailures,
    sse.stabilizeMetadataByCallId,
  ]);

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
    const restLogs = debugLogsData?.entries ?? [];
    if (sse.debugLogs.length === 0) return restLogs;
    const seen = new Set(restLogs.map(l => `${l.timestamp}|${l.message}`));
    const newLogs = sse.debugLogs.filter(l => !seen.has(`${l.timestamp}|${l.message}`));
    return [...restLogs, ...newLogs];
  }, [debugLogsData?.entries, sse.debugLogs]);

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
  const veyruExtrasForChat =
    restData.scenario_extras !== null && restData.scenario_extras.scenario_name === "veyru"
      ? restData.scenario_extras
      : null;
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
  const activeInstance = resolveSelectedInstance(selectedAgent, agentInstances);
  const activeAgentColor = activeInstance ? agentColorMap.get(activeInstance.agent_id) : undefined;
  const runCompleted =
    effectiveStatus === "scenario_complete" ||
    effectiveStatus === "error" ||
    effectiveStatus === "killed";

  return (
    <div className="mx-auto flex h-dvh max-w-7xl min-h-0 flex-col px-4 py-4">
      {/* Back link */}
      <Link
        href={groupPath("/runs")}
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
          {restData.replace_agent_source ? (
            <ReplaceAgentBadge
              sourceRunId={restData.replace_agent_source.source_run_id}
              replacedAgentId={restData.replace_agent_source.replaced_agent_id}
              replacementModel={restData.replace_agent_source.replacement_model}
              roundStart={restData.replace_agent_source.round_start}
            />
          ) : null}
          {restData.cross_run_replace_agent_source ? (
            <CrossRunReplaceAgentBadge
              sourceARunId={restData.cross_run_replace_agent_source.source_a_run_id}
              sourceBRunId={restData.cross_run_replace_agent_source.source_b_run_id}
              replacedAgentId={restData.cross_run_replace_agent_source.replaced_agent_id}
              importedModel={restData.cross_run_replace_agent_source.imported_model}
              roundStart={restData.cross_run_replace_agent_source.round_start}
              sourceBRoundEnd={restData.cross_run_replace_agent_source.source_b_round_end}
            />
          ) : null}
          {restData.resume_at_round_source ? (
            <ResumeAtRoundBadge
              sourceRunId={restData.resume_at_round_source.source_run_id}
              roundStart={restData.resume_at_round_source.round_start}
              roundsAfterResume={restData.resume_at_round_source.rounds_after_resume}
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
          {formatDayHeader(restData.timestamp)} · {maxRound} rounds · {channelMessages} messages ·{" "}
          {timelineEntries} events · {allAgents.length} agents
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
          {!isInProgress && !evaluationInProgress && runCompleted ? (
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

      {/* Derived runs (children) */}
      <DerivedRunsSection derivedRuns={restData.children} />

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

      {/* Regular labels (eval:* legacy labels are filtered out) */}
      {restData.labels.some(label => !label.startsWith("eval:")) ? (
        <div className="mb-3 flex shrink-0 flex-wrap gap-1.5">
          <LabelBadges
            labels={restData.labels.filter(label => !label.startsWith("eval:"))}
            size="md"
          />
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
          agentInstances={agentInstances}
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
            forkPointMessageId={restData.fork_source?.target_message_id ?? null}
            swapRoundNumber={veyruExtrasForChat?.swap_point?.round_number ?? null}
            swappedObserverDisplayNames={
              veyruExtrasForChat?.swap_point?.swapped_observer_display_names ?? []
            }
            internJoinRoundNumber={veyruExtrasForChat?.intern_join?.round_number ?? null}
            internTakeoverRoundNumber={veyruExtrasForChat?.intern_takeover?.round_number ?? null}
            replaceAgentRoundStart={restData.replace_agent_source?.round_start ?? null}
            replaceAgentReplacedAgentId={restData.replace_agent_source?.replaced_agent_id ?? null}
            replaceAgentReplacementModel={restData.replace_agent_source?.replacement_model ?? null}
            crossRunReplaceRoundStart={restData.cross_run_replace_agent_source?.round_start ?? null}
            crossRunReplacedAgentId={
              restData.cross_run_replace_agent_source?.replaced_agent_id ?? null
            }
            crossRunSourceARunId={restData.cross_run_replace_agent_source?.source_a_run_id ?? null}
            crossRunSourceBRunId={restData.cross_run_replace_agent_source?.source_b_run_id ?? null}
            scenarioName={restData.scenario_name}
            scenarioExtras={restData.scenario_extras ?? null}
            roundEndings={restData.round_endings}
            roundResults={restData.round_results}
            roundInjections={restData.round_injections}
            resumeCutoffTimestamp={
              restData.replace_agent_source?.replaced_at ?? restData.fork_source?.forked_at ?? null
            }
            agentSwapDividers={agentSwapDividers}
            activeInstanceRoundRange={
              activeInstance
                ? { start: activeInstance.round_start, end: activeInstance.round_end }
                : null
            }
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
        {activeInstance && activeAgentColor ? (
          <AgentDrawer
            instance={activeInstance}
            messages={displayEntries}
            agentColor={activeAgentColor}
            channelColorMap={channelColorMap}
            onClose={() => setSelectedAgent(null)}
            onNavigateToMessage={handleNavigateToMessage}
            onNavigateToChannel={channelId => {
              setSelectedAgent(null);
              setSelectedChannel(channelId);
            }}
            measurements={restData.evaluation?.measurements ?? null}
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

      {configPreview ? (
        <ConfigValueModal
          configKey={configPreview.key}
          value={configPreview.value}
          onClose={() => setConfigPreview(null)}
          secondaryAction={null}
        />
      ) : null}

      {(() => {
        const veyruExtras = veyruExtrasForChat;
        const swapPoint = veyruExtras?.swap_point ?? null;
        const internJoin = veyruExtras?.intern_join ?? null;
        const internTakeover = veyruExtras?.intern_takeover ?? null;
        let nextStackIndex = 0;
        const forkStackIndex = restData.fork_source !== null ? nextStackIndex++ : null;
        const swapStackIndex = swapPoint !== null ? nextStackIndex++ : null;
        const internJoinStackIndex = internJoin !== null ? nextStackIndex++ : null;
        const internTakeoverStackIndex = internTakeover !== null ? nextStackIndex++ : null;
        const replaceAgentStackIndex =
          restData.replace_agent_source !== null ? nextStackIndex++ : null;
        const crossRunReplaceStackIndex =
          restData.cross_run_replace_agent_source !== null ? nextStackIndex++ : null;

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

            {swapPoint && swapStackIndex !== null ? (
              <SwapPointFab
                stackIndex={swapStackIndex}
                roundNumber={swapPoint.round_number}
                onClick={() => scrollToDivider("swap-divider")}
              />
            ) : null}

            {internJoin && internJoinStackIndex !== null ? (
              <InternJoinFab
                stackIndex={internJoinStackIndex}
                roundNumber={internJoin.round_number}
                onClick={() => scrollToDivider("intern-join-divider")}
              />
            ) : null}

            {internTakeover && internTakeoverStackIndex !== null ? (
              <InternTakeoverFab
                stackIndex={internTakeoverStackIndex}
                roundNumber={internTakeover.round_number}
                onClick={() => scrollToDivider("intern-takeover-divider")}
              />
            ) : null}

            {restData.replace_agent_source && replaceAgentStackIndex !== null ? (
              <ReplaceAgentPointFab
                stackIndex={replaceAgentStackIndex}
                roundNumber={restData.replace_agent_source.round_start}
                onClick={() => scrollToDivider("replace-agent-divider")}
              />
            ) : null}

            {restData.cross_run_replace_agent_source && crossRunReplaceStackIndex !== null ? (
              <CrossRunReplaceAgentPointFab
                stackIndex={crossRunReplaceStackIndex}
                roundNumber={restData.cross_run_replace_agent_source.round_start}
                onClick={() => scrollToDivider("cross-run-replace-agent-divider")}
              />
            ) : null}

            {swapEvents.map(swap => (
              <AgentSwapPointFab
                key={`agent-swap-${swap.round_number}-${swap.agent_id}`}
                stackIndex={nextStackIndex++}
                roundNumber={swap.round_number}
                agentId={swap.agent_id}
                onClick={() =>
                  scrollToDivider(`agent-swap-divider-r${swap.round_number}-${swap.agent_id}`)
                }
              />
            ))}
          </>
        );
      })()}
    </div>
  );
}
