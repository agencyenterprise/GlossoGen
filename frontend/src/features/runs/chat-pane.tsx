"use client";

import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";

type AgentDetail = components["schemas"]["AgentDetail"];
type MessageDetail = components["schemas"]["MessageDetail"];

interface ChatPaneProps {
  messages: MessageDetail[];
  agents: AgentDetail[];
  selectedChannel: string | null;
  agentColorMap: Map<string, AgentColor>;
  channelColorMap: Map<string, AgentColor>;
  onSelectAgent: (agentId: string) => void;
  highlightedMessageId: string | null;
  highlightNonce: number;
}

interface MessageGroup {
  roundNumber: number;
  messages: MessageDetail[];
}

function groupByRound(messages: MessageDetail[]): MessageGroup[] {
  const groups: MessageGroup[] = [];
  let currentRound = -1;
  let currentMessages: MessageDetail[] = [];

  for (const msg of messages) {
    if (msg.round_number !== currentRound) {
      if (currentMessages.length > 0) {
        groups.push({ roundNumber: currentRound, messages: currentMessages });
      }
      currentRound = msg.round_number;
      currentMessages = [msg];
    } else {
      currentMessages.push(msg);
    }
  }
  if (currentMessages.length > 0) {
    groups.push({ roundNumber: currentRound, messages: currentMessages });
  }
  return groups;
}

export function ChatPane({
  messages,
  agents,
  selectedChannel,
  agentColorMap,
  channelColorMap,
  onSelectAgent,
  highlightedMessageId,
  highlightNonce,
}: ChatPaneProps) {
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());

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

  const filtered = useMemo(
    () =>
      selectedChannel === null ? messages : messages.filter(m => m.channel_id === selectedChannel),
    [messages, selectedChannel]
  );

  const groups = useMemo(() => groupByRound(filtered), [filtered]);
  const showChannelBadge = selectedChannel === null;

  let headerName = "all activity";
  if (selectedChannel !== null) {
    headerName = humanize(selectedChannel);
  }
  const headerDesc =
    selectedChannel === null ? "all channels, global turn order" : `#${selectedChannel}`;

  return (
    <div className="flex flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="text-sm text-muted-foreground">#</span>
        <span className="text-[13px] font-medium">{headerName}</span>
        <span className="text-xs text-muted-foreground">{headerDesc}</span>
      </div>

      <div className="flex-1 overflow-y-auto px-0 py-1">
        {groups.map(group => (
          <div key={group.roundNumber}>
            <div className="flex items-center gap-2.5 px-4 pb-1.5 pt-3.5">
              <div className="h-px flex-1 bg-border" />
              <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                Round {group.roundNumber}
              </span>
              <div className="h-px flex-1 bg-border" />
            </div>

            {group.messages.map(msg => {
              const agent = agentMap.get(msg.sender_agent_id);
              const color = agentColorMap.get(msg.sender_agent_id);
              const chColor = channelColorMap.get(msg.channel_id);

              return (
                <div
                  key={msg.message_id}
                  ref={el => {
                    if (el) {
                      messageRefs.current.set(msg.message_id, el);
                    } else {
                      messageRefs.current.delete(msg.message_id);
                    }
                  }}
                  className="flex gap-2.5 px-4 py-1 transition-colors hover:bg-muted/50"
                >
                  <div className="flex w-7 shrink-0 flex-col items-center">
                    <button
                      aria-label={`Open agent ${agent?.role_name ?? msg.sender_agent_id}`}
                      className={cn(
                        "flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-[10px] font-semibold transition-opacity hover:opacity-75",
                        color?.bg,
                        color?.fg
                      )}
                      onClick={() => onSelectAgent(msg.sender_agent_id)}
                    >
                      {agent ? deriveInitials(agent.role_name) : "??"}
                    </button>
                    <div className="flex flex-1 items-center">
                      <span className="text-[10px] font-medium leading-none text-muted-foreground/50">
                        {msg.turn_number}
                      </span>
                    </div>
                  </div>
                  <div className="min-w-0 flex-1 pr-4">
                    <div className="mb-0.5 flex flex-wrap items-baseline gap-1.5">
                      <button
                        className="text-[13px] font-medium hover:underline"
                        onClick={() => onSelectAgent(msg.sender_agent_id)}
                      >
                        {agent?.role_name ?? msg.sender_agent_id}
                      </button>
                      {showChannelBadge ? (
                        <span
                          className={cn(
                            "rounded-full px-1.5 py-px text-[10px] font-medium leading-relaxed",
                            chColor?.bg,
                            chColor?.fg
                          )}
                        >
                          #{msg.channel_id}
                        </span>
                      ) : null}
                      <span className="text-[10px] text-muted-foreground">
                        {formatTime(msg.timestamp)}
                      </span>
                    </div>
                    <ProseMarkdown className="[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]">
                      {msg.text}
                    </ProseMarkdown>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
