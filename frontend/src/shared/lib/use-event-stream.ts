"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "@/types/api.gen";
import { buildApiUrlWithToken } from "./api-client";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type ToolUseEntry = components["schemas"]["ToolUseEntry"];
type AgentDetail = components["schemas"]["AgentDetail"];
type RunStatus = components["schemas"]["RunStatus"];
type DebugLogEntry = components["schemas"]["DebugLogEntry"];

type SSESimulationStarted = components["schemas"]["SSESimulationStarted"];
type SSEAgentRegistered = components["schemas"]["SSEAgentRegistered"];
type SSEMessageSent = components["schemas"]["SSEMessageSent"];
type SSELLMResponseReceived = components["schemas"]["SSELLMResponseReceived"];
type SSESimulationEnded = components["schemas"]["SSESimulationEnded"];
type SSEToolCallInvoked = components["schemas"]["SSEToolCallInvoked"];
type SSEToolResultReceived = components["schemas"]["SSEToolResultReceived"];
type SSEAgentCostUpdated = components["schemas"]["SSEAgentCostUpdated"];
type SSEDebugLog = components["schemas"]["SSEDebugLog"];
type SSEAgentRunCycleFailed = components["schemas"]["SSEAgentRunCycleFailed"];
type SSEVeyruStabilizationJudged = components["schemas"]["SSEVeyruStabilizationJudged"];
type VeyruStabilizeMetadata = components["schemas"]["VeyruStabilizeMetadata"];
type AgentRunCycleFailedEntry = components["schemas"]["AgentRunCycleFailedEntry"];

/** State returned by the useEventStream hook. */
export interface EventStreamState {
  messages: ChannelMessage[];
  reasoning: ReasoningEntry[];
  toolUse: ToolUseEntry[];
  agents: AgentDetail[];
  channelIds: string[];
  totalMessages: number;
  status: RunStatus | null;
  isConnected: boolean;
  /** Debug log entries received via SSE. */
  debugLogs: DebugLogEntry[];
  /** Agent run-cycle failures received via SSE. */
  runCycleFailures: AgentRunCycleFailedEntry[];
  /** Total cost in USD from the simulation_ended event. */
  totalCostUsd: number;
  /** Duration in seconds from the simulation_ended event. */
  durationSeconds: number;
  /** Veyru-only: stabilize-judge metadata keyed by tool ``call_id``. Empty
   *  for non-veyru runs. Mirrors ``VeyruRunExtras.stabilize_metadata_by_call_id``
   *  but accumulated live from the SSE stream. */
  stabilizeMetadataByCallId: Record<string, VeyruStabilizeMetadata>;
}

/**
 * Connect to the SSE endpoint for a simulation run and accumulate events.
 *
 * Maintains running state of messages, reasoning, agents, and channels as
 * events arrive. Handles EventSource reconnection automatically via the
 * Last-Event-ID header. Returns the accumulated state for the component
 * to merge with any initial REST snapshot.
 */
export function useEventStream(
  runId: string,
  enabled: boolean,
  knownEventIds: Set<string>,
  retryOnFailure: boolean
): EventStreamState {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [reasoning, setReasoning] = useState<ReasoningEntry[]>([]);
  const [toolUse, setToolUse] = useState<ToolUseEntry[]>([]);
  const [agents, setAgents] = useState<AgentDetail[]>([]);
  const [channelIds, setChannelIds] = useState<string[]>([]);
  const [totalMessages, setTotalMessages] = useState(0);
  const [totalCostUsd, setTotalCostUsd] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [debugLogs, setDebugLogs] = useState<DebugLogEntry[]>([]);
  const [runCycleFailures, setRunCycleFailures] = useState<AgentRunCycleFailedEntry[]>([]);
  const [stabilizeMetadataByCallId, setStabilizeMetadataByCallId] = useState<
    Record<string, VeyruStabilizeMetadata>
  >({});

  const agentCostsRef = useRef<Map<string, number>>(new Map());
  const seenSseIdsRef = useRef<Set<string>>(new Set());
  const pendingStabilizeMetadataRef = useRef<Map<string, VeyruStabilizeMetadata[]>>(new Map());
  const knownIdsRef = useRef(knownEventIds);
  useEffect(() => {
    knownIdsRef.current = knownEventIds;
  }, [knownEventIds]);

  const resetState = useCallback(() => {
    setMessages([]);
    setReasoning([]);
    setToolUse([]);
    setAgents([]);
    setChannelIds([]);
    setTotalMessages(0);
    setStatus(null);
    setDebugLogs([]);
    setRunCycleFailures([]);
    setStabilizeMetadataByCallId({});
    agentCostsRef.current = new Map();
    seenSseIdsRef.current = new Set();
    pendingStabilizeMetadataRef.current = new Map();
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let cancelled = false;
    let activeSource: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      if (cancelled) return;

      const url = buildApiUrlWithToken({
        path: `/api/runs/${encodeURIComponent(runId)}/events`,
        searchParams: new URLSearchParams(),
      });
      const eventSource = new EventSource(url);
      activeSource = eventSource;
      let hasConnected = false;
      let errorCount = 0;

      eventSource.onopen = () => {
        hasConnected = true;
        errorCount = 0;
        setIsConnected(true);
      };

      eventSource.onerror = () => {
        setIsConnected(false);
        errorCount += 1;

        // Server rejected the connection (e.g. 409 — simulation not running yet).
        // EventSource goes to CLOSED and won't auto-reconnect.
        const serverRejected = eventSource.readyState === EventSource.CLOSED;

        if (!hasConnected && (serverRejected || errorCount >= 3)) {
          eventSource.close();
          activeSource = null;
          if (retryOnFailure && !cancelled) {
            retryTimer = setTimeout(connect, 2000);
          }
        }
      };

      /** Return true if this event_id was already processed (REST snapshot or prior SSE). */
      function isDuplicate(eventId: string): boolean {
        if (knownIdsRef.current.has(eventId)) return true;
        if (seenSseIdsRef.current.has(eventId)) return true;
        seenSseIdsRef.current.add(eventId);
        return false;
      }

      eventSource.addEventListener("simulation_started", (e: MessageEvent) => {
        const data: SSESimulationStarted = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        setChannelIds(data.channel_ids);
      });

      eventSource.addEventListener("agent_registered", (e: MessageEvent) => {
        const data: SSEAgentRegistered = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        const agent: AgentDetail = {
          agent_id: data.agent_id,
          role_name: data.role_name,
          channel_ids: data.channel_ids,
          tool_names: data.tool_names,
          model: data.model,
          provider: data.provider,
          system_prompt: data.system_prompt,
        };
        setAgents(prev => [...prev, agent]);
      });

      eventSource.addEventListener("message_sent", (e: MessageEvent) => {
        const data: SSEMessageSent = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        const msg = data.message;

        const channelMessage: ChannelMessage = {
          message_id: msg.message_id,
          channel_id: msg.channel_id,
          sender_agent_id: msg.sender_agent_id,
          sender_display_name: "",
          text: msg.text,
          timestamp: msg.timestamp,
          round_number: data.round_number,
          token_count: data.token_count,
        };
        setMessages(prev => [...prev, channelMessage]);
        setTotalMessages(prev => prev + 1);
      });

      eventSource.addEventListener("llm_response_received", (e: MessageEvent) => {
        const data: SSELLMResponseReceived = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        if (data.text != null && data.text.trim() !== "") {
          const entry: ReasoningEntry = {
            message_id: data.event_id,
            sender_agent_id: data.agent_id,
            text: data.text,
            timestamp: data.timestamp,
            round_number: data.round_number,
            channel_ids: [],
          };
          setReasoning(prev => [...prev, entry]);
        }
      });

      eventSource.addEventListener("tool_call_invoked", (e: MessageEvent) => {
        const data: SSEToolCallInvoked = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        setToolUse(prev => {
          if (prev.some(t => t.call_id === data.call_id)) {
            return prev;
          }
          const entry: ToolUseEntry = {
            message_id: `${data.event_id}-${data.call_id}`,
            sender_agent_id: data.agent_id,
            tool_name: data.tool_name,
            call_id: data.call_id,
            arguments: data.arguments,
            result: null,
            timestamp: data.timestamp,
            result_timestamp: null,
            round_number: data.round_number,
            result_round_number: null,
          };
          return [...prev, entry];
        });
      });

      eventSource.addEventListener("tool_result_received", (e: MessageEvent) => {
        const data: SSEToolResultReceived = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        if (data.tool_name === "stabilize_veyru") {
          const queue = pendingStabilizeMetadataRef.current.get(data.agent_id);
          if (queue && queue.length > 0) {
            const attachedMetadata = queue.shift();
            if (attachedMetadata !== undefined) {
              setStabilizeMetadataByCallId(prev => ({
                ...prev,
                [data.call_id]: attachedMetadata,
              }));
            }
          }
        }
        setToolUse(prev => {
          const existing = prev.find(t => t.call_id === data.call_id);
          if (existing) {
            return prev.map(t =>
              t.call_id === data.call_id
                ? {
                    ...t,
                    result: data.result,
                    result_timestamp: data.timestamp,
                    result_round_number: data.round_number,
                  }
                : t
            );
          }
          // Safety fallback: tool_call_invoked did not arrive first. Create
          // the entry now so the tool result still shows in the UI.
          const entry: ToolUseEntry = {
            message_id: `${data.event_id}-${data.call_id}`,
            sender_agent_id: data.agent_id,
            tool_name: data.tool_name,
            call_id: data.call_id,
            arguments: data.arguments,
            result: data.result,
            timestamp: data.timestamp,
            result_timestamp: data.timestamp,
            round_number: data.round_number,
            result_round_number: data.round_number,
          };
          return [...prev, entry];
        });
      });

      eventSource.addEventListener("veyru_stabilization_judged", (e: MessageEvent) => {
        const data: SSEVeyruStabilizationJudged = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        const metadata: VeyruStabilizeMetadata = {
          expected_actions: data.expected_actions,
          judge_match: data.judge_match,
          judge_explanation: data.judge_explanation,
        };
        const queueMap = pendingStabilizeMetadataRef.current;
        const existing = queueMap.get(data.agent_id) ?? [];
        existing.push(metadata);
        queueMap.set(data.agent_id, existing);
      });

      eventSource.addEventListener("simulation_ended", (e: MessageEvent) => {
        const data: SSESimulationEnded = JSON.parse(e.data);
        setStatus(data.reason);
        setTotalMessages(data.total_messages);
        setTotalCostUsd(data.total_cost_usd);
        setDurationSeconds(data.duration_seconds);
        eventSource.close();
        setIsConnected(false);
      });

      eventSource.addEventListener("agent_cost_updated", (e: MessageEvent) => {
        const data: SSEAgentCostUpdated = JSON.parse(e.data);
        const costs = agentCostsRef.current;
        costs.set(data.agent_id, data.cumulative_cost_usd);
        let sum = 0;
        for (const v of costs.values()) {
          sum += v;
        }
        setTotalCostUsd(sum);
      });

      eventSource.addEventListener("agent_run_cycle_failed", (e: MessageEvent) => {
        const data: SSEAgentRunCycleFailed = JSON.parse(e.data);
        if (isDuplicate(data.event_id)) return;
        const entry: AgentRunCycleFailedEntry = {
          message_id: data.event_id,
          agent_id: data.agent_id,
          timestamp: data.timestamp,
          round_number: data.round_number,
          cycle: data.cycle,
          error_type: data.error_type,
          message: data.message,
        };
        setRunCycleFailures(prev => [...prev, entry]);
      });

      eventSource.addEventListener("debug_log", (e: MessageEvent) => {
        const data: SSEDebugLog = JSON.parse(e.data);
        const entry: DebugLogEntry = {
          timestamp: data.timestamp,
          logger_name: data.logger_name,
          level: data.level,
          message: data.message,
        };
        setDebugLogs(prev => [...prev, entry]);
      });
    }

    connect();

    return () => {
      cancelled = true;
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
      }
      if (activeSource !== null) {
        activeSource.close();
      }
      resetState();
    };
  }, [runId, enabled, retryOnFailure, resetState]);

  return {
    messages,
    reasoning,
    toolUse,
    agents,
    channelIds,
    totalMessages,
    status,
    isConnected,
    debugLogs,
    runCycleFailures,
    totalCostUsd,
    durationSeconds,
    stabilizeMetadataByCallId,
  };
}
