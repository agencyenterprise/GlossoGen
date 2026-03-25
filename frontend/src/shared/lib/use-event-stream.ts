"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "@/types/api.gen";
import { API_URL } from "./api-client";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type AgentDetail = components["schemas"]["AgentDetail"];
type RunStatus = components["schemas"]["RunStatus"];
type DebugLogEntry = components["schemas"]["DebugLogEntry"];

type SSESimulationStarted = components["schemas"]["SSESimulationStarted"];
type SSEAgentRegistered = components["schemas"]["SSEAgentRegistered"];
type SSEMessageSent = components["schemas"]["SSEMessageSent"];
type SSELLMResponseReceived = components["schemas"]["SSELLMResponseReceived"];
type SSERoundAdvanced = components["schemas"]["SSERoundAdvanced"];
type SSESimulationEnded = components["schemas"]["SSESimulationEnded"];
type SSETokenDelta = components["schemas"]["SSETokenDelta"];
type SSEMessagePreview = components["schemas"]["SSEMessagePreview"];
type SSEDebugLog = components["schemas"]["SSEDebugLog"];

/** Partial message being composed by an agent. */
export interface PartialMessage {
  channelId: string;
  text: string;
}

/** State returned by the useEventStream hook. */
export interface EventStreamState {
  messages: ChannelMessage[];
  reasoning: ReasoningEntry[];
  agents: AgentDetail[];
  channelIds: string[];
  totalMessages: number;
  status: RunStatus | null;
  isConnected: boolean;
  /** Map of agent_id -> partial text for in-progress LLM responses (reasoning). */
  partialText: Map<string, string>;
  /** Agent ID currently generating a response. */
  streamingAgentId: string | null;
  /** Map of agent_id -> partial message for in-progress send_message tool calls. */
  partialMessages: Map<string, PartialMessage>;
  /** Current round number from the latest RoundAdvanced event. */
  currentRound: number;
  /** Debug log entries received via SSE. */
  debugLogs: DebugLogEntry[];
}

/**
 * Connect to the SSE endpoint for a simulation run and accumulate events.
 *
 * Maintains running state of messages, reasoning, agents, and channels as
 * events arrive. Returns the accumulated state for the component
 * to merge with any initial REST snapshot.
 */
export function useEventStream(
  runId: string,
  enabled: boolean,
  knownEventIds: Set<string>
): EventStreamState {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [reasoning, setReasoning] = useState<ReasoningEntry[]>([]);
  const [agents, setAgents] = useState<AgentDetail[]>([]);
  const [channelIds, setChannelIds] = useState<string[]>([]);
  const [totalMessages, setTotalMessages] = useState(0);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [partialText, setPartialText] = useState<Map<string, string>>(new Map());
  const [streamingAgentId, setStreamingAgentId] = useState<string | null>(null);
  const [partialMessages, setPartialMessages] = useState<Map<string, PartialMessage>>(new Map());
  const [currentRound, setCurrentRound] = useState(0);
  const [debugLogs, setDebugLogs] = useState<DebugLogEntry[]>([]);

  const knownIdsRef = useRef(knownEventIds);
  useEffect(() => {
    knownIdsRef.current = knownEventIds;
  }, [knownEventIds]);

  // Refs for values accessed inside event listener closures
  const totalMessagesRef = useRef(0);
  const currentRoundRef = useRef(0);

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
    setAgents([]);
    setChannelIds([]);
    setTotalMessages(0);
    setStatus(null);
    setPartialText(new Map());
    setStreamingAgentId(null);
    setPartialMessages(new Map());
    setCurrentRound(0);
    setDebugLogs([]);
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

    eventSource.onopen = () => {
      setIsConnected(true);
    };

    eventSource.onerror = () => {
      setIsConnected(false);
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

    eventSource.addEventListener("round_advanced", (e: MessageEvent) => {
      const data: SSERoundAdvanced = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      currentRoundRef.current = data.round_number;
      setCurrentRound(data.round_number);
    });

    eventSource.addEventListener("turn_assigned", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      currentRoundRef.current = data.round_number;
      setCurrentRound(data.round_number);
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
        turn_number: totalMessagesRef.current,
        round_number: currentRoundRef.current,
      };
      setMessages(prev => [...prev, channelMessage]);
      totalMessagesRef.current += 1;
      setTotalMessages(prev => prev + 1);

      // Clear partial text and message preview for this agent
      setPartialText(prev => {
        if (!prev.has(msg.sender_agent_id)) return prev;
        const next = new Map(prev);
        next.delete(msg.sender_agent_id);
        return next;
      });
      setPartialMessages(prev => {
        if (!prev.has(msg.sender_agent_id)) return prev;
        const next = new Map(prev);
        next.delete(msg.sender_agent_id);
        return next;
      });
      setStreamingAgentId(prev => {
        if (prev === msg.sender_agent_id) return null;
        return prev;
      });
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
          turn_number: totalMessagesRef.current,
          round_number: currentRoundRef.current,
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
      setStreamingAgentId(prev => {
        if (prev === data.agent_id) return null;
        return prev;
      });
    });

    eventSource.addEventListener("simulation_ended", (e: MessageEvent) => {
      const data: SSESimulationEnded = JSON.parse(e.data);
      setStatus(data.reason);
      setTotalMessages(data.total_messages);
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
        setStreamingAgentId(prev => {
          if (prev === agentId) return null;
          return prev;
        });
      } else {
        setStreamingAgentId(agentId);
        const pending = pendingDeltasRef.current;
        const existing = pending.get(agentId) ?? "";
        pending.set(agentId, existing + data.text);
        if (rafIdRef.current === null) {
          rafIdRef.current = requestAnimationFrame(flushTokenDeltas);
        }
      }
    });

    // Message preview events are paced by the backend (~30ms intervals)
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
            next.set(agentId, { channelId: existing.channelId, text: existing.text + data.text });
          } else {
            next.set(agentId, { channelId: data.channel_id, text: data.text });
          }
          return next;
        });
      }
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
    agents,
    channelIds,
    totalMessages,
    status,
    isConnected,
    partialText,
    streamingAgentId,
    partialMessages,
    currentRound,
    debugLogs,
  };
}
