"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Download, Pencil, Play, X } from "lucide-react";
import { API_URL } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { ToolCallDisplay } from "./tool-call-display";
import type { PendingEdit } from "./use-fork";

type AgentDetail = components["schemas"]["AgentDetail"];

interface ChatPaneProps {
  runId: string;
  messages: DisplayEntry[];
  agents: AgentDetail[];
  selectedChannel: string | null;
  agentColorMap: Map<string, AgentColor>;
  channelColorMap: Map<string, AgentColor>;
  onSelectAgent: (agentId: string) => void;
  highlightedMessageId: string | null;
  highlightNonce: number;
  /** Agent ID currently streaming a response. */
  streamingAgentIds: Set<string>;
  /** Whether the fork editing UI is enabled (only for completed/errored runs). */
  forkEnabled: boolean;
  /** The message_id currently being edited, or null. */
  editingMessageId: string | null;
  /** Saved edits awaiting fork. */
  pendingEdits: Map<string, PendingEdit>;
  /** Callbacks for fork editing. */
  onStartEdit: (messageId: string) => void;
  onSaveEdit: (messageId: string, newText: string) => void;
  onCancelEdit: () => void;
  onRemoveEdit: (messageId: string) => void;
  onForkFromMessage: (targetMessageId: string) => void;
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
  runId,
  messages,
  agents,
  selectedChannel,
  agentColorMap,
  channelColorMap,
  onSelectAgent,
  highlightedMessageId,
  highlightNonce,
  streamingAgentIds,
  forkEnabled,
  editingMessageId,
  pendingEdits,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onRemoveEdit,
  onForkFromMessage,
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

  const [showReasoning, setShowReasoning] = useState(true);
  const [showTools, setShowTools] = useState(true);

  const visibleFiltered = useMemo(() => {
    return filtered.filter(m => {
      if (m.is_reasoning && !showReasoning) return false;
      if (m.is_tool_use && !showTools) return false;
      return true;
    });
  }, [filtered, showReasoning, showTools]);

  const rounds = useMemo(() => groupByRoundAndTurn(visibleFiltered), [visibleFiltered]);

  return (
    <div className="relative flex flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="text-sm text-muted-foreground">#</span>
        <span className="text-[13px] font-medium">{headerName}</span>
        <span className="text-xs text-muted-foreground">{headerDesc}</span>
        {headerMembers ? (
          <span className="ml-auto text-[11px] text-muted-foreground">{headerMembers}</span>
        ) : null}
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground select-none">
          <input
            type="checkbox"
            checked={showReasoning}
            onChange={e => setShowReasoning(e.target.checked)}
            className="h-3 w-3 rounded border-border accent-foreground"
          />
          Reasoning
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground select-none">
          <input
            type="checkbox"
            checked={showTools}
            onChange={e => setShowTools(e.target.checked)}
            className="h-3 w-3 rounded border-border accent-foreground"
          />
          Tools
        </label>
        <button
          aria-label="Export PDF"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={() => {
            const params = new URLSearchParams();
            if (selectedChannel !== null) {
              params.set("channel_id", selectedChannel);
            }
            const qs = params.toString();
            const url = `${API_URL}/api/runs/${runId}/export/pdf${qs ? `?${qs}` : ""}`;
            window.open(url, "_blank");
          }}
        >
          <Download className="h-3.5 w-3.5" />
        </button>
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
                    {turn.entries.map((entry, entryIdx) => {
                      const entryChColor = channelColorMap.get(entry.channel_id);
                      const isEditing = editingMessageId === entry.message_id;
                      const pendingEdit = pendingEdits.get(entry.message_id);
                      const displayText = pendingEdit ? pendingEdit.newText : entry.text;
                      const canEdit =
                        forkEnabled &&
                        !entry.is_reasoning &&
                        !entry.is_tool_use &&
                        !entry.is_partial;
                      const entryKey = `${entry.message_id}-${entry.is_reasoning ? "r" : entry.is_tool_use ? "t" : "m"}-${entryIdx}`;

                      return (
                        <div
                          key={entryKey}
                          ref={el => {
                            if (el) {
                              messageRefs.current.set(entry.message_id, el);
                            } else {
                              messageRefs.current.delete(entry.message_id);
                            }
                          }}
                          className={cn(
                            "group/entry relative",
                            entry.is_reasoning && "ml-4 opacity-50",
                            entry.is_tool_use && "ml-4",
                            pendingEdit &&
                              "rounded-md bg-amber-50/50 ring-1 ring-amber-200/50 dark:bg-amber-950/20 dark:ring-amber-800/30"
                          )}
                        >
                          {entry.is_reasoning ? (
                            <span className="text-[10px] italic text-muted-foreground">
                              {entry.is_partial ? "streaming..." : "reasoning"}
                            </span>
                          ) : entry.is_tool_use ? null : showChannelBadge ? (
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

                          {entry.is_tool_use ? (
                            <ToolCallDisplay
                              toolName={entry.tool_name}
                              arguments={entry.tool_arguments}
                              result={entry.tool_result}
                            />
                          ) : isEditing ? (
                            <MessageEditor
                              initialText={displayText}
                              onSave={newText => onSaveEdit(entry.message_id, newText)}
                              onCancel={onCancelEdit}
                            />
                          ) : (
                            <>
                              {displayText ? (
                                <ProseMarkdown className="[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]">
                                  {displayText}
                                </ProseMarkdown>
                              ) : null}
                              {entry.is_partial ? (
                                <span className="inline-block h-3 w-1.5 animate-pulse bg-foreground/60" />
                              ) : null}

                              {/* Edit / fork controls */}
                              {canEdit ? (
                                <span className="absolute -right-1 top-0 flex items-center gap-0.5 opacity-0 transition-opacity group-hover/entry:opacity-100">
                                  {pendingEdit ? (
                                    <>
                                      <button
                                        aria-label="Play from this message"
                                        className="rounded p-0.5 text-green-600 transition-colors hover:bg-green-100 dark:text-green-400 dark:hover:bg-green-900/30"
                                        onClick={() => onForkFromMessage(entry.message_id)}
                                      >
                                        <Play className="h-3 w-3" />
                                      </button>
                                      <button
                                        aria-label="Remove edit"
                                        className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                        onClick={() => onRemoveEdit(entry.message_id)}
                                      >
                                        <X className="h-3 w-3" />
                                      </button>
                                    </>
                                  ) : (
                                    <button
                                      aria-label="Edit message"
                                      className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                      onClick={() => onStartEdit(entry.message_id)}
                                    >
                                      <Pencil className="h-3 w-3" />
                                    </button>
                                  )}
                                </span>
                              ) : null}
                            </>
                          )}
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

      {/* Status bar */}
      <div className="flex shrink-0 items-center justify-between border-t border-border px-4 py-1.5">
        {streamingAgentIds.size > 0 ? (
          <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" />
            {[...streamingAgentIds].map(id => agentMap.get(id)?.role_name ?? id).join(", ")}{" "}
            {streamingAgentIds.size === 1 ? "is" : "are"} typing...
          </span>
        ) : (
          <span />
        )}
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

function MessageEditor({
  initialText,
  onSave,
  onCancel,
}: {
  initialText: string;
  onSave: (newText: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initialText);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  return (
    <div className="flex flex-col gap-1.5 py-1">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={e => setText(e.target.value)}
        className="min-h-[60px] w-full resize-y rounded-md border border-border bg-background px-2 py-1.5 text-[13px] focus:outline-none focus:ring-1 focus:ring-ring"
        onKeyDown={e => {
          if (e.key === "Escape") {
            onCancel();
          }
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            onSave(text);
          }
        }}
      />
      <div className="flex items-center gap-1.5">
        <button
          className="rounded-md bg-foreground px-2.5 py-0.5 text-[11px] font-medium text-background transition-opacity hover:opacity-80"
          onClick={() => onSave(text)}
        >
          Save
        </button>
        <button
          className="rounded-md border border-border px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={onCancel}
        >
          Cancel
        </button>
        <span className="text-[10px] text-muted-foreground">Ctrl+Enter to save, Esc to cancel</span>
      </div>
    </div>
  );
}
