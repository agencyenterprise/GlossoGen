"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import {
  ArrowLeftRight,
  ChevronDown,
  Download,
  FolderArchive,
  Hash,
  Package,
  Pencil,
  UserCog,
  UserPlus,
} from "lucide-react";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { NotificationDisplay } from "./notification-display";
import { ToolCallDisplay } from "./tool-call-display";
import { RunCycleFailureDisplay } from "./run-cycle-failure-display";
import { RoundTimelineModal } from "./round-timeline-modal";
import type { PendingEdit } from "./use-fork";

type AgentDetail = components["schemas"]["AgentDetail"];
type VeyruCaseSummary = components["schemas"]["VeyruCaseSummary"];
type RoundEnding = components["schemas"]["RoundEnding"];

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
  /** Per-round Veyru case metadata (empty for non-Veyru scenarios). */
  veyruCases: VeyruCaseSummary[];
  /** One entry per completed round describing why its main phase ended. */
  roundEndings: RoundEnding[];
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
  veyruCases,
  roundEndings,
}: ChatPaneProps) {
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const innerContentRef = useRef<HTMLDivElement>(null);
  const roundMarkerRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const isAtBottomRef = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [currentVisibleRound, setCurrentVisibleRound] = useState<number | null>(null);
  const prevScrollHeightRef = useRef(0);
  const [hoveredCallId, setHoveredCallId] = useState<string | null>(null);
  const [timelineRound, setTimelineRound] = useState<number | null>(null);

  const messagesByRound = useMemo(() => {
    const byRound = new Map<number, DisplayEntry[]>();
    for (const msg of messages) {
      const list = byRound.get(msg.round_number);
      if (list) {
        list.push(msg);
      } else {
        byRound.set(msg.round_number, [msg]);
      }
    }
    return byRound;
  }, [messages]);

  const caseByRound = useMemo(() => {
    const byRound = new Map<number, VeyruCaseSummary>();
    for (const c of veyruCases) {
      byRound.set(c.round_number, c);
    }
    return byRound;
  }, [veyruCases]);

  const endingByRound = useMemo(() => {
    const byRound = new Map<number, RoundEnding>();
    for (const e of roundEndings) {
      byRound.set(e.round_number, e);
    }
    return byRound;
  }, [roundEndings]);

  // Imperative jump — does NOT go through React state. On large runs the
  // entry list (and wire SVG) is fully mounted in the DOM, so any state
  // update would force a full reconciliation before useEffect could scroll,
  // adding ~1–2s of pre-scroll latency. Acting directly on the DOM keeps
  // the click-to-scroll instant.
  const jumpToMessage = useCallback((messageId: string) => {
    const el = messageRefs.current.get(messageId);
    if (!el) return;
    el.scrollIntoView({ behavior: "instant", block: "center" });
    el.classList.remove("animate-highlight");
    // Force reflow so the animation restarts even if the class was just removed.
    void el.offsetWidth;
    el.classList.add("animate-highlight");
    window.setTimeout(() => {
      el.classList.remove("animate-highlight");
    }, 1500);
  }, []);

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
    // Instant jump, not smooth — smooth-scroll duration scales with distance
    // and becomes very slow on long runs. The highlight flash draws the eye to
    // the landing spot.
    el.scrollIntoView({ behavior: "instant", block: "center" });
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

  const notificationPairs = useMemo(() => {
    const out: Array<{ callMessageId: string; resultMessageId: string; callId: string }> = [];
    for (const e of filtered) {
      if (e.is_notification_result && e.paired_message_id !== "") {
        out.push({
          callMessageId: e.paired_message_id,
          resultMessageId: e.message_id,
          callId: e.call_id,
        });
      }
    }
    return out;
  }, [filtered]);

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

  // Track which round's separator is nearest the top of the scroll viewport
  // so the floating indicator reflects what the user is currently reading.
  useEffect(() => {
    const scrollEl = scrollContainerRef.current;
    if (!scrollEl) return undefined;
    const updateCurrent = () => {
      const scrollTop = scrollEl.scrollTop;
      let current: number | null = null;
      for (const [round, el] of roundMarkerRefs.current.entries()) {
        if (el.offsetTop <= scrollTop + 24) {
          if (current === null || round > current) {
            current = round;
          }
        }
      }
      if (current === null && roundMarkerRefs.current.size > 0) {
        current = Math.min(...roundMarkerRefs.current.keys());
      }
      setCurrentVisibleRound(current);
    };

    const raf = requestAnimationFrame(updateCurrent);
    scrollEl.addEventListener("scroll", updateCurrent, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      scrollEl.removeEventListener("scroll", updateCurrent);
    };
  }, [rounds]);

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
              void downloadAuthenticatedFile({
                path: `/api/runs/${runId}/export/pdf`,
                searchParams: params,
                fallbackFilename: `${runId.slice(0, 8)}_transcript.pdf`,
              });
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
              void downloadAuthenticatedFile({
                path: `/api/runs/${runId}/export/artifacts`,
                searchParams: new URLSearchParams(),
                fallbackFilename: `${runId.slice(0, 8)}_artifacts.tar.gz`,
              });
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
              void downloadAuthenticatedFile({
                path: `/api/runs/${runId}/export/bundle`,
                searchParams: new URLSearchParams(),
                fallbackFilename: `${runId.slice(0, 8)}_bundle.tar.gz`,
              });
            }}
          >
            <Package className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      </div>

      {currentVisibleRound !== null ? (
        <div className="absolute left-1/2 top-12 z-30 -translate-x-1/2">
          <button
            type="button"
            aria-label={`Open round ${currentVisibleRound} timeline`}
            onClick={() => setTimelineRound(currentVisibleRound)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
          >
            <Hash className="h-3 w-3" />
            Round {currentVisibleRound}
          </button>
        </div>
      ) : null}

      {timelineRound !== null ? (
        <RoundTimelineModal
          roundNumber={timelineRound}
          messages={messagesByRound.get(timelineRound) ?? []}
          veyruCase={caseByRound.get(timelineRound) ?? null}
          roundEnding={endingByRound.get(timelineRound) ?? null}
          onClose={() => setTimelineRound(null)}
        />
      ) : null}

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-0 py-1"
        onScroll={handleScroll}
      >
        <div ref={innerContentRef} className="relative">
          <ConnectionWires
            pairs={notificationPairs}
            messageRefs={messageRefs}
            containerRef={innerContentRef}
            hoveredCallId={hoveredCallId}
          />
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
                    Channel history was wiped. Round {round.roundNumber} begins with the new
                    pairings.
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
              <div
                ref={el => {
                  if (el === null) {
                    roundMarkerRefs.current.delete(round.roundNumber);
                  } else {
                    roundMarkerRefs.current.set(round.roundNumber, el);
                  }
                }}
                data-round-marker={round.roundNumber}
                className="flex items-center gap-2.5 px-4 pb-1.5 pt-3.5"
              >
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
                        const canEdit =
                          forkEnabled &&
                          !entry.is_reasoning &&
                          !entry.is_tool_use &&
                          !entry.is_notification_result &&
                          !entry.is_run_cycle_failure;

                        const entryKindKey = entry.is_reasoning
                          ? "r"
                          : entry.is_tool_use
                            ? "t"
                            : entry.is_notification_result
                              ? "n"
                              : entry.is_run_cycle_failure
                                ? "f"
                                : "m";
                        const entryKey = `${entry.message_id}-${entryKindKey}-${entryIdx}`;
                        const hasLinkedPair = entry.paired_message_id !== "";
                        const isLinkHovered = hasLinkedPair && hoveredCallId === entry.call_id;

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
                            onMouseEnter={
                              hasLinkedPair ? () => setHoveredCallId(entry.call_id) : undefined
                            }
                            onMouseLeave={hasLinkedPair ? () => setHoveredCallId(null) : undefined}
                            onClick={
                              hasLinkedPair
                                ? () => jumpToMessage(entry.paired_message_id)
                                : undefined
                            }
                            className={cn(
                              "group/entry relative",
                              entry.is_reasoning &&
                                "ml-4 rounded-md border border-border/60 bg-muted/35 px-2 py-1.5 text-muted-foreground dark:bg-muted/20",
                              !entry.is_reasoning &&
                                !entry.is_tool_use &&
                                !entry.is_notification_result &&
                                !entry.is_run_cycle_failure &&
                                "rounded-md border border-border/70 bg-background px-2 py-1.5 shadow-sm",
                              (entry.is_tool_use ||
                                entry.is_notification_result ||
                                entry.is_run_cycle_failure) &&
                                "ml-4",
                              hasLinkedPair && "cursor-pointer",
                              isLinkHovered &&
                                "rounded-md ring-2 ring-blue-400/40 dark:ring-blue-500/40",
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
                            ) : entry.is_tool_use ||
                              entry.is_notification_result ||
                              entry.is_run_cycle_failure ? null : showChannelBadge ? (
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

                            {entry.is_tool_use || entry.is_notification_result ? (
                              <ToolOrNotification entry={entry} />
                            ) : entry.is_run_cycle_failure ? (
                              <RunCycleFailureDisplay
                                errorType={entry.error_type}
                                message={entry.text}
                                cycle={entry.cycle}
                              />
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
                                !entry.is_notification_result &&
                                !entry.is_run_cycle_failure &&
                                entry.character_count > 0 ? (
                                  <span className="mt-0.5 block text-[10px] text-muted-foreground/60">
                                    {entry.character_count.toLocaleString()} characters
                                  </span>
                                ) : null}
                                {!entry.is_reasoning &&
                                !entry.is_tool_use &&
                                !entry.is_notification_result &&
                                !entry.is_run_cycle_failure ? (
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
                                          void downloadAuthenticatedFile({
                                            path: `/api/runs/${runId}/export/artifacts/${entry.message_id}`,
                                            searchParams: new URLSearchParams(),
                                            fallbackFilename: `${runId.slice(0, 8)}_${entry.message_id.slice(0, 8)}_artifacts.tar.gz`,
                                          });
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

interface NotificationPair {
  callMessageId: string;
  resultMessageId: string;
  callId: string;
}

interface WireShape {
  callId: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
}

/** Deterministic hue from a call_id so each wire gets a stable unique color. */
function hueFromCallId(callId: string): number {
  let h = 0;
  for (let i = 0; i < callId.length; i += 1) {
    h = (h * 31 + callId.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

/** Renders curved SVG wires inside the scrollable content connecting each
 *  read_notifications call pill to its response chip. Each wire is a cubic
 *  bezier that bulges out to the left of the column. Wires re-measure on
 *  layout changes via ResizeObserver + MutationObserver so they stay aligned
 *  as entries expand or new messages arrive. */
function ConnectionWires({
  pairs,
  messageRefs,
  containerRef,
  hoveredCallId,
}: {
  pairs: NotificationPair[];
  messageRefs: RefObject<Map<string, HTMLDivElement>>;
  containerRef: RefObject<HTMLDivElement | null>;
  hoveredCallId: string | null;
}) {
  const [wires, setWires] = useState<WireShape[]>([]);

  useLayoutEffect(() => {
    let rafId: number | null = null;
    let attemptsLeft = 60;
    let ro: ResizeObserver | null = null;
    let mo: MutationObserver | null = null;

    function schedule() {
      if (rafId !== null) return;
      rafId = requestAnimationFrame(recompute);
    }

    function recompute() {
      rafId = null;
      const containerEl = containerRef.current;
      if (containerEl === null) {
        // Container not yet mounted — retry next frame.
        if (attemptsLeft > 0) {
          attemptsLeft -= 1;
          rafId = requestAnimationFrame(recompute);
        }
        return;
      }
      // Attach observers once, as soon as the container exists. The
      // ResizeObserver catches layout shifts (entry expansion, window resize).
      // The MutationObserver catches late-mounting entries on huge runs
      // streamed in after our initial rAF retry budget is exhausted.
      if (ro === null) {
        ro = new ResizeObserver(schedule);
        ro.observe(containerEl);
      }
      if (mo === null) {
        mo = new MutationObserver(schedule);
        mo.observe(containerEl, { childList: true, subtree: true });
      }
      const containerRect = containerEl.getBoundingClientRect();
      const next: WireShape[] = [];
      for (const pair of pairs) {
        const callEl = messageRefs.current.get(pair.callMessageId);
        const resultEl = messageRefs.current.get(pair.resultMessageId);
        if (callEl === undefined || resultEl === undefined) continue;
        const callRect = callEl.getBoundingClientRect();
        const resultRect = resultEl.getBoundingClientRect();
        const callMid = callRect.top + callRect.height / 2 - containerRect.top;
        const resultMid = resultRect.top + resultRect.height / 2 - containerRect.top;
        const callX = callRect.left - containerRect.left;
        const resultX = resultRect.left - containerRect.left;
        next.push({
          callId: pair.callId,
          startX: callX,
          startY: callMid,
          endX: resultX,
          endY: resultMid,
          color: `hsl(${hueFromCallId(pair.callId)}, 72%, 55%)`,
        });
      }
      setWires(prev => {
        if (prev.length !== next.length) return next;
        for (let i = 0; i < prev.length; i += 1) {
          const a = prev[i];
          const b = next[i];
          if (a === undefined || b === undefined) return next;
          if (
            a.callId !== b.callId ||
            Math.abs(a.startY - b.startY) > 0.5 ||
            Math.abs(a.endY - b.endY) > 0.5 ||
            Math.abs(a.startX - b.startX) > 0.5 ||
            Math.abs(a.endX - b.endX) > 0.5
          ) {
            return next;
          }
        }
        return prev;
      });
      // Refs on large runs can attach across many paints. Keep retrying on
      // animation frames until every pair is measured, then stop. Further
      // updates come from the ResizeObserver for layout shifts.
      if (next.length < pairs.length && attemptsLeft > 0) {
        attemptsLeft -= 1;
        rafId = requestAnimationFrame(recompute);
      }
    }

    recompute();
    return () => {
      if (rafId !== null) cancelAnimationFrame(rafId);
      if (ro !== null) ro.disconnect();
      if (mo !== null) mo.disconnect();
    };
  }, [pairs, messageRefs, containerRef]);

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ overflow: "visible" }}
      aria-hidden="true"
    >
      {wires.map(w => {
        const dy = Math.abs(w.endY - w.startY);
        // Bulge leftward; proportional to vertical distance, capped.
        const bulge = Math.min(80, Math.max(24, dy * 0.25));
        const c1x = w.startX - bulge;
        const c2x = w.endX - bulge;
        const d = `M ${w.startX} ${w.startY} C ${c1x} ${w.startY}, ${c2x} ${w.endY}, ${w.endX} ${w.endY}`;
        const isHovered = hoveredCallId === w.callId;
        return (
          <g key={w.callId}>
            <path
              d={d}
              stroke={w.color}
              strokeWidth={isHovered ? 2.5 : 1.5}
              strokeOpacity={isHovered ? 0.95 : 0.55}
              strokeLinecap="round"
              fill="none"
            />
            <circle cx={w.startX} cy={w.startY} r={isHovered ? 3.5 : 2.5} fill={w.color} />
            <circle cx={w.endX} cy={w.endY} r={isHovered ? 3.5 : 2.5} fill={w.color} />
          </g>
        );
      })}
    </svg>
  );
}

/** Renders either the notification chip (for split notification-result entries)
 *  or the generic tool-call pill. The split between read_notifications call and
 *  its response happens upstream in mergeEntries; here we only pick a renderer. */
function ToolOrNotification({ entry }: { entry: DisplayEntry }) {
  if (entry.is_notification_result) {
    return <NotificationDisplay result={entry.tool_result} />;
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
