"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { components } from "@/types/api.gen";
import { API_URL } from "./api-client";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type AgentDetail = components["schemas"]["AgentDetail"];
type RunStatus = components["schemas"]["RunStatus"];

type SSESimulationStarted = components["schemas"]["SSESimulationStarted"];
type SSEAgentRegistered = components["schemas"]["SSEAgentRegistered"];
type SSETurnAssigned = components["schemas"]["SSETurnAssigned"];
type SSEMessageSent = components["schemas"]["SSEMessageSent"];
type SSELLMResponseReceived = components["schemas"]["SSELLMResponseReceived"];
type SSESimulationEnded = components["schemas"]["SSESimulationEnded"];
type SSETokenDelta = components["schemas"]["SSETokenDelta"];
type SSEMessagePreview = components["schemas"]["SSEMessagePreview"];

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
  totalTurns: number;
  status: RunStatus | null;
  isConnected: boolean;
  /** Map of agent_id -> partial text for in-progress LLM responses (reasoning). */
  partialText: Map<string, string>;
  /** Agent ID currently generating a response. */
  streamingAgentId: string | null;
  /** Map of agent_id -> partial message for in-progress send_message tool calls. */
  partialMessages: Map<string, PartialMessage>;
  /** Map of agent_id -> current turn number (from turn_assigned events). */
  agentTurns: Map<string, number>;
  /** Map of agent_id -> current round number (from turn_assigned events). */
  agentRounds: Map<string, number>;
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
  initialAgentRounds: Map<string, number>
): EventStreamState {
  const [messages, setMessages] = useState<ChannelMessage[]>([]);
  const [reasoning, setReasoning] = useState<ReasoningEntry[]>([]);
  const [agents, setAgents] = useState<AgentDetail[]>([]);
  const [channelIds, setChannelIds] = useState<string[]>([]);
  const [totalTurns, setTotalTurns] = useState(0);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [partialText, setPartialText] = useState<Map<string, string>>(new Map());
  const [streamingAgentId, setStreamingAgentId] = useState<string | null>(null);
  const [partialMessages, setPartialMessages] = useState<Map<string, PartialMessage>>(new Map());
  const [agentTurns, setAgentTurns] = useState<Map<string, number>>(new Map());
  const [agentRounds, setAgentRounds] = useState<Map<string, number>>(new Map());

  // Refs mirror the state for synchronous access inside event listeners.
  // Seeded from REST data so SSE messages arriving before any turn_assigned
  // still get correct turn/round numbers.
  const agentTurnRef = useRef<Map<string, number>>(new Map());
  const agentRoundRef = useRef<Map<string, number>>(new Map());
  const knownIdsRef = useRef(knownEventIds);
  useEffect(() => {
    knownIdsRef.current = knownEventIds;
  }, [knownEventIds]);

  // Seed turn/round refs and state from REST data
  useEffect(() => {
    if (initialAgentTurns.size > 0) {
      for (const [id, turn] of initialAgentTurns) {
        agentTurnRef.current.set(id, turn);
      }
      setAgentTurns(new Map(agentTurnRef.current));
    }
    if (initialAgentRounds.size > 0) {
      for (const [id, round] of initialAgentRounds) {
        agentRoundRef.current.set(id, round);
      }
      setAgentRounds(new Map(agentRoundRef.current));
    }
  }, [initialAgentTurns, initialAgentRounds]);

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
    setTotalTurns(0);
    setStatus(null);
    setPartialText(new Map());
    setStreamingAgentId(null);
    setPartialMessages(new Map());
    setAgentTurns(new Map());
    setAgentRounds(new Map());
    agentTurnRef.current = new Map();
    agentRoundRef.current = new Map();
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

    eventSource.addEventListener("turn_assigned", (e: MessageEvent) => {
      const data: SSETurnAssigned = JSON.parse(e.data);
      if (knownIdsRef.current.has(data.event_id)) return;
      agentTurnRef.current.set(data.agent_id, data.turn_number);
      agentRoundRef.current.set(data.agent_id, data.round_number);
      setAgentTurns(new Map(agentTurnRef.current));
      setAgentRounds(new Map(agentRoundRef.current));
      setTotalTurns(data.turn_number);
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
        turn_number: agentTurnRef.current.get(msg.sender_agent_id) ?? 0,
        round_number: agentRoundRef.current.get(msg.sender_agent_id) ?? 0,
      };
      setMessages(prev => [...prev, channelMessage]);

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
          turn_number: agentTurnRef.current.get(data.agent_id) ?? 0,
          round_number: agentRoundRef.current.get(data.agent_id) ?? 0,
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
      setTotalTurns(data.total_turns);
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
            next.set(agentId, { channelId: existing.channelId, text: existing.text + data.text });
          } else {
            next.set(agentId, { channelId: data.channel_id, text: data.text });
          }
          return next;
        });
      }
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
    totalTurns,
    status,
    isConnected,
    partialText,
    streamingAgentId,
    partialMessages,
    agentTurns,
    agentRounds,
  };
}
