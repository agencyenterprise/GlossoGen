"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "@/types/api.gen";
import { API_URL } from "./api-client";

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
type SSETokenDelta = components["schemas"]["SSETokenDelta"];
type SSEMessagePreview = components["schemas"]["SSEMessagePreview"];
type SSEToolResultReceived = components["schemas"]["SSEToolResultReceived"];
type SSEAgentCostUpdated = components["schemas"]["SSEAgentCostUpdated"];
type SSEDebugLog = components["schemas"]["SSEDebugLog"];

/** Partial message being composed by an agent. */
export interface PartialMessage {
  channelId: string;
  text: string;
  roundNumber: number;
}

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
  /** Map of agent_id -> partial text for in-progress LLM responses (reasoning). */
  partialText: Map<string, string>;
  /** Set of agent IDs currently generating responses. */
  streamingAgentIds: Set<string>;
  /** Map of agent_id -> partial message for in-progress send_message tool calls. */
  partialMessages: Map<string, PartialMessage>;
  /** Map of agent_id -> current turn number. */
  agentTurns: Map<string, number>;
  /** Debug log entries received via SSE. */
  debugLogs: DebugLogEntry[];
  /** Total cost in USD from the simulation_ended event. */
  totalCostUsd: number;
  /** Duration in seconds from the simulation_ended event. */
  durationSeconds: number;
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
  initialAgentTurns: Map<string, number>,
  initialMessageCount: number
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
  const [partialText, setPartialText] = useState<Map<string, string>>(new Map());
  const [streamingAgentIds, setStreamingAgentIds] = useState<Set<string>>(new Set());
  const [partialMessages, setPartialMessages] = useState<Map<string, PartialMessage>>(new Map());
  const [agentTurns, setAgentTurns] = useState<Map<string, number>>(new Map());
  const [debugLogs, setDebugLogs] = useState<DebugLogEntry[]>([]);

  // Refs mirror the state for synchronous access inside event listeners.
  const agentTurnRef = useRef<Map<string, number>>(new Map());
  // Global message counter used as fallback turn_number.
  const messageCounterRef = useRef(0);
  const agentCostsRef = useRef<Map<string, number>>(new Map());
  const knownIdsRef = useRef(knownEventIds);
  useEffect(() => {
    knownIdsRef.current = knownEventIds;
  }, [knownEventIds]);

  // Seed turn refs and message counter from REST data
  useEffect(() => {
    messageCounterRef.current = initialMessageCount;
    if (initialAgentTurns.size > 0) {
      for (const [id, turn] of initialAgentTurns) {
        agentTurnRef.current.set(id, turn);
      }
      setAgentTurns(new Map(agentTurnRef.current));
    }
  }, [initialAgentTurns, initialMessageCount]);

  // Buffer for batching token deltas via requestAnimationFrame
  const pendingDeltasRef = useRef<Map<string, string>>(new Map());
  const rafIdRef = useRef<number | null>(null);

  const flushTokenDeltas = useCallback(() => {
    rafIdRef.current = null;
    const pending = pendingDeltasRef.current;
    if (pending.size === 0) return;

    const snapshot = new Map(pending);
    pending.clear();

    setPartialText(prev => {
      const next = new Map(prev);
      for (const [agentId, text] of snapshot) {
        const existing = next.get(agentId) ?? "";
        next.set(agentId, existing + text);
      }
      return next;
    });
  }, []);

  const resetState = useCallback(() => {
    setMessages([]);
    setReasoning([]);
    setToolUse([]);
    setAgents([]);
    setChannelIds([]);
    setTotalMessages(0);
    setStatus(null);
    setPartialText(new Map());
    setStreamingAgentIds(new Set());
    setPartialMessages(new Map());
    setAgentTurns(new Map());
    setDebugLogs([]);
    agentTurnRef.current = new Map();
    agentCostsRef.current = new Map();
    messageCounterRef.current = 0;
    pendingDeltasRef.current = new Map();
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    const url = `${API_URL}/api/runs/${encodeURIComponent(runId)}/events`;
    const eventSource = new EventSource(url);
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
      // If the SSE endpoint rejects the connection repeatedly (e.g. simulation
      // already ended and stream.json was cleaned up), close the EventSource
      // so the parent component falls back to the REST status.
      if (!hasConnected && errorCount >= 3) {
        eventSource.close();
      }
    };

    eventSource.addEventListener("simulation_started", (e: MessageEvent) => {
      const data: SSESimulationStarted = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      setChannelIds(data.channel_ids);
    });

    eventSource.addEventListener("agent_registered", (e: MessageEvent) => {
      const data: SSEAgentRegistered = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      const agent: AgentDetail = {
        agent_id: data.agent_id,
        role_name: data.role_name,
        channel_ids: data.channel_ids,
        tool_names: data.tool_names,
        model: data.model,
        system_prompt: data.system_prompt,
      };
      setAgents(prev => [...prev, agent]);
    });

    eventSource.addEventListener("message_sent", (e: MessageEvent) => {
      const data: SSEMessageSent = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      const msg = data.message;

      messageCounterRef.current += 1;

      const channelMessage: ChannelMessage = {
        message_id: msg.message_id,
        channel_id: msg.channel_id,
        sender_agent_id: msg.sender_agent_id,
        text: msg.text,
        timestamp: msg.timestamp,
        turn_number: agentTurnRef.current.get(msg.sender_agent_id) ?? messageCounterRef.current,
        round_number: data.round_number,
      };
      setMessages(prev => [...prev, channelMessage]);
      setTotalMessages(prev => prev + 1);

      // Clear message preview for this agent (the message was sent successfully).
      // Do NOT clear partialText or streamingAgentIds — the agent may still be
      // streaming reasoning for subsequent tool calls within the same run cycle.
      setPartialMessages(prev => {
        if (!prev.has(msg.sender_agent_id)) return prev;
        const next = new Map(prev);
        next.delete(msg.sender_agent_id);
        return next;
      });
    });

    eventSource.addEventListener("llm_response_received", (e: MessageEvent) => {
      const data: SSELLMResponseReceived = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      if (data.text != null && data.text.trim() !== "") {
        messageCounterRef.current += 1;
        const entry: ReasoningEntry = {
          message_id: data.event_id,
          sender_agent_id: data.agent_id,
          text: data.text,
          timestamp: data.timestamp,
          turn_number: agentTurnRef.current.get(data.agent_id) ?? messageCounterRef.current,
          round_number: data.round_number,
          channel_ids: [],
        };
        setReasoning(prev => [...prev, entry]);
      }

      // Clear partial text for this agent (LLM response is complete)
      setPartialText(prev => {
        if (!prev.has(data.agent_id)) return prev;
        const next = new Map(prev);
        next.delete(data.agent_id);
        return next;
      });
      setStreamingAgentIds(prev => {
        if (!prev.has(data.agent_id)) return prev;
        const next = new Set(prev);
        next.delete(data.agent_id);
        return next;
      });
    });

    eventSource.addEventListener("tool_result_received", (e: MessageEvent) => {
      const data: SSEToolResultReceived = JSON.parse(e.data);
      // Create a new tool use entry or update an existing one with the result
      setToolUse(prev => {
        const existing = prev.find(t => t.call_id === data.call_id);
        if (existing) {
          return prev.map(t => (t.call_id === data.call_id ? { ...t, result: data.result } : t));
        }
        messageCounterRef.current += 1;
        const entry: ToolUseEntry = {
          message_id: data.event_id,
          sender_agent_id: data.agent_id,
          tool_name: data.tool_name,
          call_id: data.call_id,
          arguments: data.arguments,
          result: data.result,
          timestamp: data.timestamp,
          turn_number: agentTurnRef.current.get(data.agent_id) ?? messageCounterRef.current,
          round_number: data.round_number,
        };
        return [...prev, entry];
      });
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

    eventSource.addEventListener("token_delta", (e: MessageEvent) => {
      const data: SSETokenDelta = JSON.parse(e.data);
      const agentId = data.agent_id;

      if (data.is_final) {
        pendingDeltasRef.current.delete(agentId);
        setPartialText(prev => {
          if (!prev.has(agentId)) return prev;
          const next = new Map(prev);
          next.delete(agentId);
          return next;
        });
        setStreamingAgentIds(prev => {
          if (!prev.has(agentId)) return prev;
          const next = new Set(prev);
          next.delete(agentId);
          return next;
        });
      } else {
        setStreamingAgentIds(prev => {
          if (prev.has(agentId)) return prev;
          const next = new Set(prev);
          next.add(agentId);
          return next;
        });
        const pending = pendingDeltasRef.current;
        const existing = pending.get(agentId) ?? "";
        pending.set(agentId, existing + data.text);
        if (rafIdRef.current === null) {
          rafIdRef.current = requestAnimationFrame(flushTokenDeltas);
        }
      }
    });

    // Message preview events are paced by the backend (~30ms intervals)
    // so we update state directly on each event instead of RAF-batching.
    eventSource.addEventListener("message_preview", (e: MessageEvent) => {
      const data: SSEMessagePreview = JSON.parse(e.data);
      const agentId = data.agent_id;

      if (data.is_final) {
        setPartialMessages(prev => {
          if (!prev.has(agentId)) return prev;
          const next = new Map(prev);
          next.delete(agentId);
          return next;
        });
      } else {
        setPartialMessages(prev => {
          const next = new Map(prev);
          const existing = next.get(agentId);
          if (existing) {
            next.set(agentId, {
              channelId: existing.channelId,
              text: existing.text + data.text,
              roundNumber: data.round_number,
            });
          } else {
            next.set(agentId, {
              channelId: data.channel_id,
              text: data.text,
              roundNumber: data.round_number,
            });
          }
          return next;
        });
      }
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

    return () => {
      eventSource.close();
      resetState();
    };
  }, [runId, enabled, resetState, flushTokenDeltas]);

  return {
    messages,
    reasoning,
    toolUse,
    agents,
    channelIds,
    totalMessages,
    status,
    isConnected,
    partialText,
    streamingAgentIds,
    partialMessages,
    agentTurns,
    debugLogs,
    totalCostUsd,
    durationSeconds,
  };
}
