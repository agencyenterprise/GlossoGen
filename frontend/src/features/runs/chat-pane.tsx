"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftRight,
  ChevronDown,
  Download,
  FolderArchive,
  Package,
  Pencil,
  UserCog,
  UserPlus,
} from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { buildApiUrlWithToken } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import {
  NotificationDisplay,
  parseNotificationResult,
  TOOL_NAME_READ_NOTIFICATIONS,
} from "./notification-display";
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
  onForkFromMessage: (targetMessageId: string) => void;
  /** The message_id that was the fork point, if this is a forked run. */
  forkPointMessageId: string | null;
  /** Round number where the first post-swap messages appear (if the run had an observer swap). */
  swapRoundNumber: number | null;
  /** Display names of the two observers that swapped teams. */
  swappedObserverDisplayNames: string[];
  /** Round number where the intern joined the link (if intern mode was enabled). */
  internJoinRoundNumber: number | null;
  /** Round number where the intern replaced the field observer (if intern mode was enabled). */
  internTakeoverRoundNumber: number | null;
}

interface TurnGroup {
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
        agentId: msg.sender_agent_id,
        timestamp: msg.timestamp,
        entries: [msg],
      };
    } else if (currentTurn && msg.sender_agent_id === currentTurn.agentId) {
      currentTurn.entries.push(msg);
    } else {
      if (currentTurn) {
        currentTurns.push(currentTurn);
      }
      currentTurn = {
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
  forkEnabled,
  editingMessageId,
  pendingEdits,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onForkFromMessage,
  forkPointMessageId,
  swapRoundNumber,
  swappedObserverDisplayNames,
  internJoinRoundNumber,
  internTakeoverRoundNumber,
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
    return messages.filter(m => m.channel_ids.includes(selectedChannel));
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
    <div className="relative flex min-h-0 flex-col overflow-hidden">
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
        <span className="group/pdf relative">
          <button
            aria-label="Export PDF"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => {
              const params = new URLSearchParams();
              if (selectedChannel !== null) {
                params.set("channel_id", selectedChannel);
              }
              const url = buildApiUrlWithToken({
                path: `/api/runs/${runId}/export/pdf`,
                searchParams: params,
              });
              window.open(url, "_blank");
            }}
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <span className="pointer-events-none absolute left-1/2 top-full z-50 mt-1 hidden -translate-x-1/2 whitespace-nowrap rounded-md border border-border bg-background px-2 py-1 text-[11px] shadow-lg group-hover/pdf:block">
            Export PDF
          </span>
        </span>
        <Tooltip label="Download all artifacts">
          <button
            aria-label="Download artifacts"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => {
              const url = buildApiUrlWithToken({
                path: `/api/runs/${runId}/export/artifacts`,
                searchParams: new URLSearchParams(),
              });
              window.open(url, "_blank");
            }}
          >
            <FolderArchive className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
        <Tooltip label="Export full bundle">
          <button
            aria-label="Export bundle (with git history)"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => {
              const url = buildApiUrlWithToken({
                path: `/api/runs/${runId}/export/bundle`,
                searchParams: new URLSearchParams(),
              });
              window.open(url, "_blank");
            }}
          >
            <Package className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-0 py-1"
        onScroll={handleScroll}
      >
        {rounds.map((round, roundIdx) => (
          <div key={`round-${roundIdx}-${round.roundNumber}`}>
            {swapRoundNumber !== null && round.roundNumber === swapRoundNumber ? (
              <div
                id="swap-divider"
                className="mx-4 my-4 rounded-md border-2 border-dashed border-amber-400/80 bg-amber-50 px-4 py-3 dark:border-amber-600/70 dark:bg-amber-950/50"
              >
                <div className="flex items-center justify-center gap-2 text-amber-800 dark:text-amber-200">
                  <ArrowLeftRight className="h-4 w-4" />
                  <span className="text-sm font-semibold">
                    {swappedObserverDisplayNames.length === 2 ? (
                      <>
                        {swappedObserverDisplayNames[0]} <span aria-hidden="true">⇄</span>{" "}
                        {swappedObserverDisplayNames[1]} — swapped teams
                      </>
                    ) : (
                      <>Observers swapped between teams</>
                    )}
                  </span>
                </div>
                <div className="mt-1 text-center text-[11px] text-amber-700/80 dark:text-amber-300/80">
                  Channel history was wiped. Round {round.roundNumber} begins with the new pairings.
                </div>
              </div>
            ) : null}
            {internJoinRoundNumber !== null && round.roundNumber === internJoinRoundNumber ? (
              <div
                id="intern-join-divider"
                className="mx-4 my-4 rounded-md border-2 border-dashed border-emerald-400/80 bg-emerald-50 px-4 py-3 dark:border-emerald-600/70 dark:bg-emerald-950/50"
              >
                <div className="flex items-center justify-center gap-2 text-emerald-800 dark:text-emerald-200">
                  <UserPlus className="h-4 w-4" />
                  <span className="text-sm font-semibold">
                    Intern Observer joined the comm link
                  </span>
                </div>
                <div className="mt-1 text-center text-[11px] text-emerald-700/80 dark:text-emerald-300/80">
                  Silent observation begins at round {round.roundNumber}. The intern cannot see
                  messages from earlier rounds.
                </div>
              </div>
            ) : null}
            {internTakeoverRoundNumber !== null &&
            round.roundNumber === internTakeoverRoundNumber ? (
              <div
                id="intern-takeover-divider"
                className="mx-4 my-4 rounded-md border-2 border-dashed border-violet-400/80 bg-violet-50 px-4 py-3 dark:border-violet-600/70 dark:bg-violet-950/50"
              >
                <div className="flex items-center justify-center gap-2 text-violet-800 dark:text-violet-200">
                  <UserCog className="h-4 w-4" />
                  <span className="text-sm font-semibold">
                    Intern Observer took over as Field Observer
                  </span>
                </div>
                <div className="mt-1 text-center text-[11px] text-violet-700/80 dark:text-violet-300/80">
                  The previous Field Observer left the comm link. Round {round.roundNumber} begins
                  with the new pairing.
                </div>
              </div>
            ) : null}
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
                  key={`${roundIdx}-${turnIdx}-${turn.agentId}`}
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
                        {turnIdx + 1}
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
                      const canEdit = forkEnabled && !entry.is_reasoning && !entry.is_tool_use;

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
                            entry.is_reasoning &&
                              "ml-4 rounded-md border border-border/60 bg-muted/35 px-2 py-1.5 text-muted-foreground dark:bg-muted/20",
                            !entry.is_reasoning &&
                              !entry.is_tool_use &&
                              "rounded-md border border-border/70 bg-background px-2 py-1.5 shadow-sm",
                            entry.is_tool_use && "ml-4",
                            pendingEdit &&
                              "rounded-md bg-amber-50/50 ring-1 ring-amber-200/50 dark:bg-amber-950/20 dark:ring-amber-800/30",
                            forkPointMessageId === entry.message_id &&
                              "rounded-md bg-blue-50/60 px-2 py-1.5 ring-1 ring-blue-300/50 dark:bg-blue-950/30 dark:ring-blue-700/40"
                          )}
                        >
                          {forkPointMessageId === entry.message_id ? (
                            <span className="mb-0.5 inline-block rounded-full bg-blue-100 px-1.5 py-px text-[10px] font-medium leading-relaxed text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                              fork point (edited)
                            </span>
                          ) : null}

                          {entry.is_reasoning ? (
                            <span className="mb-1 inline-block rounded-full border border-border/70 bg-background/80 px-1.5 py-px text-[10px] font-medium text-muted-foreground">
                              reasoning
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
                            <ToolOrNotification entry={entry} />
                          ) : isEditing ? (
                            <MessageEditor
                              initialText={displayText}
                              onFork={newText => {
                                onSaveEdit(entry.message_id, newText);
                                onForkFromMessage(entry.message_id);
                              }}
                              onCancel={onCancelEdit}
                            />
                          ) : (
                            <>
                              {displayText ? (
                                <ProseMarkdown
                                  className={cn(
                                    !entry.is_reasoning && "text-foreground",
                                    "[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]"
                                  )}
                                >
                                  {displayText}
                                </ProseMarkdown>
                              ) : null}
                              {!entry.is_reasoning &&
                              !entry.is_tool_use &&
                              entry.character_count > 0 ? (
                                <span className="mt-0.5 block text-[10px] text-muted-foreground/60">
                                  {entry.character_count.toLocaleString()} characters
                                </span>
                              ) : null}
                              {!entry.is_reasoning && !entry.is_tool_use ? (
                                <span className="absolute right-1 top-1 z-10 flex items-center gap-0.5 rounded-md bg-background/90 p-1 shadow-sm opacity-0 transition-opacity group-hover/entry:opacity-100">
                                  {canEdit ? (
                                    <Tooltip label="Edit &amp; fork">
                                      <button
                                        aria-label="Edit and fork from this message"
                                        className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                        onClick={() => onStartEdit(entry.message_id)}
                                      >
                                        <Pencil className="h-3 w-3" />
                                      </button>
                                    </Tooltip>
                                  ) : null}
                                  <Tooltip label="Download artifacts up to this point">
                                    <button
                                      aria-label="Download artifacts at this message"
                                      className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                      onClick={() => {
                                        const url = buildApiUrlWithToken({
                                          path: `/api/runs/${runId}/export/artifacts/${entry.message_id}`,
                                          searchParams: new URLSearchParams(),
                                        });
                                        window.open(url, "_blank");
                                      }}
                                    >
                                      <FolderArchive className="h-3 w-3" />
                                    </button>
                                  </Tooltip>
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

function MessageEditor({
  initialText,
  onFork,
  onCancel,
}: {
  initialText: string;
  onFork: (newText: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initialText);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const autoResize = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${ta.scrollHeight}px`;
  }, []);

  useEffect(() => {
    autoResize();
    textareaRef.current?.focus();
  }, [autoResize]);

  return (
    <div className="flex flex-col gap-1.5 py-1">
      <textarea
        ref={textareaRef}
        value={text}
        onChange={e => {
          setText(e.target.value);
          autoResize();
        }}
        className="w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-[13px] focus:outline-none focus:ring-1 focus:ring-ring"
        onKeyDown={e => {
          if (e.key === "Escape") {
            onCancel();
          }
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            onFork(text);
          }
        }}
      />
      <div className="flex items-center gap-1.5">
        <button
          className="rounded-md bg-foreground px-2.5 py-0.5 text-[11px] font-medium text-background transition-opacity hover:opacity-80"
          onClick={() => onFork(text)}
        >
          Fork
        </button>
        <button
          className="rounded-md border border-border px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={onCancel}
        >
          Cancel
        </button>
        <span className="text-[10px] text-muted-foreground">Ctrl+Enter to fork, Esc to cancel</span>
      </div>
    </div>
  );
}

/** Renders a tool call as either a notification display or a generic tool call.
 *  Falls back to ToolCallDisplay when the result is not a parseable notification. */
function ToolOrNotification({ entry }: { entry: DisplayEntry }) {
  if (entry.tool_name === TOOL_NAME_READ_NOTIFICATIONS) {
    const payload = parseNotificationResult(entry.tool_result);
    if (payload) {
      return <NotificationDisplay result={entry.tool_result} />;
    }
  }
  return (
    <ToolCallDisplay
      toolName={entry.tool_name}
      arguments={entry.tool_arguments}
      result={entry.tool_result}
      stabilizeMetadata={entry.stabilize_metadata}
    />
  );
}
