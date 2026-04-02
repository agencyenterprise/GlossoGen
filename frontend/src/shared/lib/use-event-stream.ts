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
type SSEToolResultReceived = components["schemas"]["SSEToolResultReceived"];
type SSEAgentCostUpdated = components["schemas"]["SSEAgentCostUpdated"];
type SSEDebugLog = components["schemas"]["SSEDebugLog"];

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
  knownEventIds: Set<string>
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

  const agentCostsRef = useRef<Map<string, number>>(new Map());
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
    agentCostsRef.current = new Map();
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

      const channelMessage: ChannelMessage = {
        message_id: msg.message_id,
        channel_id: msg.channel_id,
        sender_agent_id: msg.sender_agent_id,
        text: msg.text,
        timestamp: msg.timestamp,
        round_number: data.round_number,
      };
      setMessages(prev => [...prev, channelMessage]);
      setTotalMessages(prev => prev + 1);
    });

    eventSource.addEventListener("llm_response_received", (e: MessageEvent) => {
      const data: SSELLMResponseReceived = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
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

    eventSource.addEventListener("tool_result_received", (e: MessageEvent) => {
      const data: SSEToolResultReceived = JSON.parse(e.data);
      setToolUse(prev => {
        const existing = prev.find(t => t.call_id === data.call_id);
        if (existing) {
          return prev.map(t => (t.call_id === data.call_id ? { ...t, result: data.result } : t));
        }
        const entry: ToolUseEntry = {
          message_id: data.event_id,
          sender_agent_id: data.agent_id,
          tool_name: data.tool_name,
          call_id: data.call_id,
          arguments: data.arguments,
          result: data.result,
          timestamp: data.timestamp,
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
  }, [runId, enabled, resetState]);

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
    totalCostUsd,
    durationSeconds,
  };
}
