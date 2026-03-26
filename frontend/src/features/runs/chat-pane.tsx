"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type AgentDetail = components["schemas"]["AgentDetail"];

interface ChatPaneProps {
  messages: DisplayEntry[];
  agents: AgentDetail[];
  selectedChannel: string | null;
  agentColorMap: Map<string, AgentColor>;
  channelColorMap: Map<string, AgentColor>;
  onSelectAgent: (agentId: string) => void;
  highlightedMessageId: string | null;
  highlightNonce: number;
  /** Agent ID currently streaming a response. */
  streamingAgentId: string | null;
}

interface TurnGroup {
  turnNumber: number;
  agentId: string;
  timestamp: string;
  entries: DisplayEntry[];
}

interface RoundGroup {
  roundNumber: number;
  turns: TurnGroup[];
}

function groupByRoundAndTurn(messages: DisplayEntry[]): RoundGroup[] {
  const rounds: RoundGroup[] = [];
  let currentRound = -1;
  let currentTurns: TurnGroup[] = [];
  let currentTurn: TurnGroup | null = null;

  for (const msg of messages) {
    if (msg.round_number !== currentRound) {
      if (currentTurn) {
        currentTurns.push(currentTurn);
      }
      if (currentTurns.length > 0) {
        rounds.push({ roundNumber: currentRound, turns: currentTurns });
      }
      currentRound = msg.round_number;
      currentTurns = [];
      currentTurn = {
        turnNumber: msg.turn_number,
        agentId: msg.sender_agent_id,
        timestamp: msg.timestamp,
        entries: [msg],
      };
    } else if (
      currentTurn &&
      msg.turn_number === currentTurn.turnNumber &&
      msg.sender_agent_id === currentTurn.agentId
    ) {
      currentTurn.entries.push(msg);
    } else {
      if (currentTurn) {
        currentTurns.push(currentTurn);
      }
      currentTurn = {
        turnNumber: msg.turn_number,
        agentId: msg.sender_agent_id,
        timestamp: msg.timestamp,
        entries: [msg],
      };
    }
  }
  if (currentTurn) {
    currentTurns.push(currentTurn);
  }
  if (currentTurns.length > 0) {
    rounds.push({ roundNumber: currentRound, turns: currentTurns });
  }
  return rounds;
}

/** Threshold in pixels for considering the user "at the bottom" of the scroll area. */
const SCROLL_BOTTOM_THRESHOLD = 80;

export function ChatPane({
  messages,
  agents,
  selectedChannel,
  agentColorMap,
  channelColorMap,
  onSelectAgent,
  highlightedMessageId,
  highlightNonce,
  streamingAgentId,
}: ChatPaneProps) {
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const prevScrollHeightRef = useRef(0);

  // Scroll to bottom on initial render so the user sees the latest messages
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
        prevScrollHeightRef.current = el.scrollHeight;
      });
    }
  }, []);

  // Track scroll position to determine if user is at the bottom.
  // When the user scrolls up to read history we stop auto-scrolling;
  // once they scroll back down past the threshold we resume.
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_BOTTOM_THRESHOLD;
    isAtBottomRef.current = atBottom;
    setIsAtBottom(atBottom);
    prevScrollHeightRef.current = el.scrollHeight;
  }, []);

  // A MutationObserver catches all content changes (new messages, partial
  // streaming text, reasoning expansion) and scrolls to the bottom when the
  // user was already there. This avoids tracking individual state updates.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return undefined;

    const observer = new MutationObserver(() => {
      if (!isAtBottomRef.current) return;
      if (el.scrollHeight <= prevScrollHeightRef.current) return;
      prevScrollHeightRef.current = el.scrollHeight;
      el.scrollTop = el.scrollHeight;
    });

    observer.observe(el, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, []);

  useEffect(() => {
    if (!highlightedMessageId) {
      return undefined;
    }
    const el = messageRefs.current.get(highlightedMessageId);
    if (!el) {
      return undefined;
    }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("animate-highlight");
    const timeout = setTimeout(() => {
      el.classList.remove("animate-highlight");
    }, 1500);
    return () => clearTimeout(timeout);
  }, [highlightedMessageId, highlightNonce]);

  const agentMap = useMemo(() => {
    const map = new Map<string, AgentDetail>();
    for (const a of agents) {
      map.set(a.agent_id, a);
    }
    return map;
  }, [agents]);

  const filtered = useMemo(() => {
    if (selectedChannel === null) {
      return messages;
    }
    return messages.filter(m => m.is_reasoning || m.channel_ids.includes(selectedChannel));
  }, [messages, selectedChannel]);

  const rounds = useMemo(() => groupByRoundAndTurn(filtered), [filtered]);
  const showChannelBadge = selectedChannel === null;

  let headerName = "all activity";
  if (selectedChannel !== null) {
    headerName = humanize(selectedChannel);
  }

  const headerMembers = useMemo(() => {
    if (selectedChannel === null) {
      return null;
    }
    const members = agents
      .filter(a => a.channel_ids.includes(selectedChannel))
      .map(a => a.role_name);
    if (members.length === 0) {
      return null;
    }
    return members.join(", ");
  }, [selectedChannel, agents]);

  const headerDesc =
    selectedChannel === null ? "all channels, global turn order" : `#${selectedChannel}`;

  return (
    <div className="relative flex flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="text-sm text-muted-foreground">#</span>
        <span className="text-[13px] font-medium">{headerName}</span>
        <span className="text-xs text-muted-foreground">{headerDesc}</span>
        {headerMembers ? (
          <span className="ml-auto text-[11px] text-muted-foreground">{headerMembers}</span>
        ) : null}
        {streamingAgentId ? (
          <span className="ml-auto flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
            {agentMap.get(streamingAgentId)?.role_name ?? streamingAgentId} is typing...
          </span>
        ) : null}
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-0 py-1"
        onScroll={handleScroll}
      >
        {rounds.map((round, roundIdx) => (
          <div key={`round-${roundIdx}-${round.roundNumber}`}>
            <div className="flex items-center gap-2.5 px-4 pb-1.5 pt-3.5">
              <div className="h-px flex-1 bg-border" />
              <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                Round {round.roundNumber}
              </span>
              <div className="h-px flex-1 bg-border" />
            </div>

            {round.turns.map((turn, turnIdx) => {
              const agent = agentMap.get(turn.agentId);
              const color = agentColorMap.get(turn.agentId);

              return (
                <div
                  key={`${roundIdx}-${turnIdx}-${turn.turnNumber}-${turn.agentId}`}
                  className="flex gap-2.5 px-4 py-1 transition-colors hover:bg-muted/50"
                >
                  <div className="flex w-7 shrink-0 flex-col items-start">
                    <button
                      aria-label={`Open agent ${agent?.role_name ?? turn.agentId}`}
                      className={cn(
                        "flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-[10px] font-semibold transition-opacity hover:opacity-75",
                        color?.bg,
                        color?.fg
                      )}
                      onClick={() => onSelectAgent(turn.agentId)}
                    >
                      {agent ? deriveInitials(agent.role_name) : "??"}
                    </button>
                    <div className="flex flex-1 items-center justify-center self-stretch">
                      <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                        {turn.turnNumber}
                      </span>
                    </div>
                  </div>
                  <div className="min-w-0 flex-1 pr-4">
                    <div className="mb-0.5 flex flex-wrap items-baseline gap-1.5">
                      <button
                        className="text-[13px] font-medium hover:underline"
                        onClick={() => onSelectAgent(turn.agentId)}
                      >
                        {agent?.role_name ?? turn.agentId}
                      </button>
                      <span className="text-[10px] text-muted-foreground">
                        {formatTime(turn.timestamp)}
                      </span>
                    </div>
                    {turn.entries.map(entry => {
                      const entryChColor = channelColorMap.get(entry.channel_id);
                      return (
                        <div
                          key={entry.message_id}
                          ref={el => {
                            if (el) {
                              messageRefs.current.set(entry.message_id, el);
                            } else {
                              messageRefs.current.delete(entry.message_id);
                            }
                          }}
                          className={cn(entry.is_reasoning && "ml-4 opacity-50")}
                        >
                          {entry.is_reasoning ? (
                            <span className="text-[10px] italic text-muted-foreground">
                              {entry.is_partial ? "streaming..." : "reasoning"}
                            </span>
                          ) : showChannelBadge ? (
                            <span
                              className={cn(
                                "mb-0.5 inline-block rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed",
                                entryChColor?.bg,
                                entryChColor?.fg
                              )}
                            >
                              #{entry.channel_id}
                            </span>
                          ) : null}
                          <ProseMarkdown className="[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]">
                            {entry.text}
                          </ProseMarkdown>
                          {entry.is_partial ? (
                            <span className="inline-block h-3 w-1.5 animate-pulse bg-foreground/60" />
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Auto-scroll status bar */}
      <div className="flex shrink-0 items-center justify-center border-t border-border px-4 py-1.5">
        {isAtBottom ? (
          <span className="text-[11px] text-muted-foreground">Auto-scroll enabled</span>
        ) : (
          <button
            className="flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-0.5 text-[11px] font-medium text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
            onClick={scrollToBottom}
          >
            <ChevronDown className="h-3 w-3" />
            Scroll to bottom
          </button>
        )}
      </div>
    </div>
  );
}
