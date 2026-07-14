"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/lib/api-client";
import { useEventStream } from "@/shared/lib/use-event-stream";
import { buildAgentColorMap, buildChannelColorMap } from "./agent-colors";
import { deriveAgentInstances } from "./agent-instance";
import type { AgentSwapDivider, ContextCompactionMarker } from "./chat-pane";
import { judgeMetadataFromExtras, mergeEntries } from "./display-entry";
import type { ScenarioPlugin } from "./scenario-plugin";

/**
 * Fetch + derive everything the run-detail view renders.
 *
 * Owns the REST snapshot query, the debug-log query, the stop mutation, and the
 * live SSE stream, then merges REST + SSE into the deduplicated display state
 * (messages/reasoning/tool-use, agents, channels, swap dividers, compaction
 * markers, debug logs). ``RunDetail`` keeps only view state (selection,
 * modals, highlight) and renders from this hook's output.
 */
export function useRunDetailData({
  scenario,
  runDirName,
  scenarioPlugin,
  evalJustLaunched,
}: {
  scenario: string;
  runDirName: string;
  scenarioPlugin: ScenarioPlugin;
  evalJustLaunched: boolean;
}) {
  const runId = `${scenario}/${runDirName}`;
  const queryClient = useQueryClient();

  // REST fetch — the full run snapshot. Polls while starting / evaluating and,
  // as a fallback, while in-progress if the live SSE stream is not connected.
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
        // SSE delivers messages, cost, and the terminal transition live, so a
        // full-detail re-pull is only needed as a fallback when the stream is
        // down. `simulation_ended` invalidates this query directly. Reading
        // `sse.isConnected` here makes the interval reactive: when the stream
        // drops, the re-render rebuilds this closure and the fallback poll
        // resumes.
        if (sseConnected) {
          return false;
        }
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
  const sse = useEventStream(runId, sseEnabled, knownEventIds, true, scenarioPlugin.liveJudge);
  const sseConnected = sse.isConnected;

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

  // If SSE was enabled (REST said in_progress) but failed to connect, the
  // simulation likely ended between the REST fetch and SSE attempt. Refetch
  // REST to get the updated status.
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
  const runCompleted =
    effectiveStatus === "scenario_complete" ||
    effectiveStatus === "error" ||
    effectiveStatus === "killed";

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

  const agentInstances = useMemo(
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

  const contextCompactionMarkers = useMemo<ContextCompactionMarker[]>(() => {
    const roleNameByAgent = new Map<string, string>();
    for (const a of allAgents) {
      roleNameByAgent.set(a.agent_id, a.role_name);
    }
    return (restData?.context_compaction_events ?? []).map(event => ({
      agent_id: event.agent_id,
      role_name: roleNameByAgent.get(event.agent_id) ?? event.agent_id,
      round_number: event.round_number,
      provider_name: event.provider_name,
      summary_char_count: event.summary_char_count,
      summary_text: event.summary_text,
    }));
  }, [allAgents, restData?.context_compaction_events]);

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
    const judgeMetadataByCallId = {
      ...judgeMetadataFromExtras(scenarioExtras),
      ...sse.judgeMetadataByCallId,
    };
    const allToolUse = [...restToolUse, ...newToolUse];
    // Let the scenario plug-in render any bespoke per-tool-call supplement
    // (e.g. the container-yard move verdict) from scenario_extras, keyed by
    // call_id. Empty for scenarios/tools whose plug-in adds nothing.
    const toolMetadataByCallId: Record<string, ReactNode> = {};
    for (const t of allToolUse) {
      const node = scenarioPlugin.renderToolMetadata({
        toolName: t.tool_name,
        callId: t.call_id,
        extras: scenarioExtras,
      });
      if (node != null) {
        toolMetadataByCallId[t.call_id] = node;
      }
    }

    return mergeEntries(
      [...restMessages, ...newMessages],
      [...restReasoning, ...newReasoning],
      allToolUse,
      [...restRunCycleFailures, ...newFailures],
      judgeMetadataByCallId,
      toolMetadataByCallId
    );
  }, [
    restData,
    sse.messages,
    sse.reasoning,
    sse.toolUse,
    sse.runCycleFailures,
    sse.judgeMetadataByCallId,
    scenarioPlugin,
  ]);

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

  const maxRound = displayEntries.reduce((max, m) => Math.max(max, m.round_number), 0);
  const scenarioMarkers = scenarioPlugin.getTimelineMarkers({
    extras: restData?.scenario_extras ?? null,
  });
  const uniqueModelKeys = [...new Set(allAgents.map(a => `${a.provider}:${a.model}`))];
  let modelLabel: string;
  if (uniqueModelKeys.length === 1) {
    modelLabel = uniqueModelKeys[0] ?? "unknown";
  } else if (uniqueModelKeys.length === 0) {
    modelLabel = "unknown";
  } else {
    modelLabel = `${uniqueModelKeys.length} models`;
  }

  const channelMessages = displayEntries.filter(
    e => !e.is_reasoning && !e.is_tool_use && !e.is_notification_result
  ).length;
  const timelineEntries = displayEntries.length;
  const restCost = restData?.total_cost_usd ?? 0;
  const totalCostUsd = Math.max(sse.totalCostUsd, restCost);
  const durationSeconds =
    sse.durationSeconds > 0 ? sse.durationSeconds : (restData?.duration_seconds ?? 0);

  return {
    runId,
    restData,
    isLoading,
    error,
    sseConnected,
    effectiveStatus,
    isInProgress,
    runCompleted,
    displayEntries,
    allAgents,
    allChannelIds,
    agentInstances,
    agentSwapDividers,
    contextCompactionMarkers,
    agentColorMap,
    channelColorMap,
    allDebugLogs,
    scenarioMarkers,
    swapEvents,
    maxRound,
    modelLabel,
    channelMessages,
    timelineEntries,
    totalCostUsd,
    durationSeconds,
    stopMutation,
  };
}
