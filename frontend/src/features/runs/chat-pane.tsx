"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Archive, ChevronDown, UserCog } from "lucide-react";
import Link from "next/link";
import { cn } from "@/shared/lib/cn";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import { deriveInitials, type AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { formatTime, humanize } from "./format";
import { ProseMarkdown } from "./prose-markdown";
import { NotificationDisplay } from "./notification-display";
import { ToolCallDisplay } from "./tool-call-display";
import { RunCycleFailureDisplay } from "./run-cycle-failure-display";
import { RoundTimelineModal } from "./round-timeline-modal";
import { RoundInjectionRow, RoundOutcomeRow } from "./round-event-row";
import type { ScenarioTimelineMarker } from "./scenario-plugin";
import { ScenarioMarkerDivider } from "./scenario-timeline-marker";
import { ChatHeader } from "./chat-header";
import { ChatRoundBadge } from "./chat-round-badge";
import { ConnectionWires } from "./connection-wires";

type AgentDetail = components["schemas"]["AgentDetail"];
type RunDetailResponse = components["schemas"]["RunDetailResponse"];
type ScenarioExtras = NonNullable<RunDetailResponse["scenario_extras"]>;
type RoundEnding = components["schemas"]["RoundEnding"];
type RoundResult = components["schemas"]["RoundResult"];
type RoundInjection = components["schemas"]["RoundInjection"];
type ReplaceAgentSource = components["schemas"]["ReplaceAgentSource"];
type CrossRunReplaceAgentSource = components["schemas"]["CrossRunReplaceAgentSource"];

interface ChatPaneProps {
  /** Export controls rendered in the channel header. The authenticated viewer
   *  passes its PDF + zip download buttons; the public demo viewer passes a
   *  static download link. Keeps ChatPane decoupled from the API client. */
  exportSlot: ReactNode;
  messages: DisplayEntry[];
  agents: AgentDetail[];
  selectedChannel: string | null;
  agentColorMap: Map<string, AgentColor>;
  channelColorMap: Map<string, AgentColor>;
  onSelectAgent: (agentId: string) => void;
  highlightedMessageId: string | null;
  highlightNonce: number;
  /** The message_id that was the fork point, if this is a forked run. */
  forkPointMessageId: string | null;
  /** Round-anchored scenario-specific markers (from the scenario plug-in), rendered as dividers at their round. */
  scenarioMarkers: ScenarioTimelineMarker[];
  /** Replace-agent provenance (round, replaced agent, replacement model), or
   *  null when this run is not a replace-agent derivation. */
  replaceAgentSource: ReplaceAgentSource | null;
  /** Cross-run replace-agent provenance (round, imported agent, source runs),
   *  or null when this run is not a cross-run derivation. */
  crossRunReplaceAgentSource: CrossRunReplaceAgentSource | null;
  /** Scenario name, used to dispatch to the scenario plug-in for the round-detail modal. */
  scenarioName: string;
  /** Scenario-specific run extras, dispatched to the scenario plug-in for the round-detail modal. Null for scenarios with no extras. */
  scenarioExtras: ScenarioExtras | null;
  /** One entry per completed round describing why its main phase ended. */
  roundEndings: RoundEnding[];
  /** Per-round, per-team pass/fail outcomes emitted by the scenario. */
  roundResults: RoundResult[];
  /** Scenario injections delivered to agents at each round boundary. */
  roundInjections: RoundInjection[];
  /** ISO timestamp at which the resume happened (replace-agent / fork). Turns and rounds with earlier timestamps are rendered faded so users see they were inherited from the source run. Null for non-resumed runs. */
  resumeCutoffTimestamp: string | null;
  /**
   * In-run scheduled agent swaps. Each entry is rendered as a slate divider
   * at the top of its ``round_number`` so the channel chat shows where the
   * pre-swap agent ends and the post-swap agent begins. Empty for runs with
   * no scheduled swaps.
   */
  agentSwapDividers: AgentSwapDivider[];
  /**
   * Provider-native history compactions. Each entry renders a marker at the top
   * of its ``round_number`` showing that the agent's context was compacted, with
   * an expandable summary when the provider returned readable text (Anthropic).
   * Empty for runs with no compaction.
   */
  contextCompactionMarkers: ContextCompactionMarker[];
  /**
   * Round range of the currently-selected agent instance (drawer open).
   * When set, the round timeline badge and jump-to-round dropdown clamp to
   * this range so the user can't navigate to rounds outside the active
   * generation's window. Null when no agent drawer is open or the active
   * instance has no upper bound.
   */
  activeInstanceRoundRange: { start: number; end: number | null } | null;
}

export interface AgentSwapDivider {
  agent_id: string;
  role_name: string;
  round_number: number;
  generation: number;
  old_model: string;
  new_model: string;
  /** Synthetic instance_key for the post-swap generation; clicking the divider opens its drawer tab. */
  post_swap_instance_key: string;
}

export interface ContextCompactionMarker {
  agent_id: string;
  role_name: string;
  round_number: number;
  provider_name: string;
  summary_char_count: number;
  /** Provider's readable summary, or "" when stored encrypted server-side (OpenAI). */
  summary_text: string;
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
  exportSlot,
  messages,
  agents,
  selectedChannel,
  agentColorMap,
  channelColorMap,
  onSelectAgent,
  highlightedMessageId,
  highlightNonce,
  forkPointMessageId,
  scenarioMarkers,
  replaceAgentSource,
  crossRunReplaceAgentSource,
  scenarioName,
  scenarioExtras,
  roundEndings,
  roundResults,
  roundInjections,
  resumeCutoffTimestamp,
  agentSwapDividers,
  contextCompactionMarkers,
  activeInstanceRoundRange,
}: ChatPaneProps) {
  const groupPath = useGroupPath();
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const innerContentRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
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

  const endingByRound = useMemo(() => {
    const byRound = new Map<number, RoundEnding>();
    for (const e of roundEndings) {
      byRound.set(e.round_number, e);
    }
    return byRound;
  }, [roundEndings]);

  const resultsByRound = useMemo(() => {
    const byRound = new Map<number, RoundResult[]>();
    for (const r of roundResults) {
      const list = byRound.get(r.round_number);
      if (list) {
        list.push(r);
      } else {
        byRound.set(r.round_number, [r]);
      }
    }
    return byRound;
  }, [roundResults]);

  const injectionsByRound = useMemo(() => {
    const byRound = new Map<number, RoundInjection[]>();
    for (const i of roundInjections) {
      const list = byRound.get(i.round_number);
      if (list) {
        list.push(i);
      } else {
        byRound.set(i.round_number, [i]);
      }
    }
    return byRound;
  }, [roundInjections]);

  const sortedRoundNumbers = useMemo(() => {
    const all = [...messagesByRound.keys()].sort((a, b) => a - b);
    if (activeInstanceRoundRange === null) {
      return all;
    }
    return all.filter(n => {
      if (n < activeInstanceRoundRange.start) return false;
      if (activeInstanceRoundRange.end !== null && n > activeInstanceRoundRange.end) return false;
      return true;
    });
  }, [messagesByRound, activeInstanceRoundRange]);

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

  const agentMap = useMemo(() => {
    const map = new Map<string, AgentDetail>();
    for (const a of agents) {
      map.set(a.agent_id, a);
    }
    return map;
  }, [agents]);

  const roleNameForAgent = useCallback(
    (agentId: string) => agentMap.get(agentId)?.role_name ?? agentId,
    [agentMap]
  );

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

  const channelMembers = useMemo(() => {
    if (selectedChannel === null) {
      return [];
    }
    return agents.filter(a => a.channel_ids.includes(selectedChannel));
  }, [selectedChannel, agents]);

  const headerDesc =
    selectedChannel === null ? "all channels, global turn order" : `#${selectedChannel}`;

  const [showReasoning, setShowReasoning] = useState(true);
  const [showTools, setShowTools] = useState(true);

  // Agent IDs the user has toggled on in the channel header to focus the view.
  // Empty = show every member. Filtering uses the intersection with the
  // current channel's members (``focusedAgentIds`` below), so a focus on a
  // member of one channel never hides all traffic in another.
  const [rawFocusedAgentIds, setRawFocusedAgentIds] = useState<Set<string>>(new Set());

  const focusedAgentIds = useMemo(() => {
    const memberIds = new Set(channelMembers.map(m => m.agent_id));
    const out = new Set<string>();
    for (const id of rawFocusedAgentIds) {
      if (memberIds.has(id)) {
        out.add(id);
      }
    }
    return out;
  }, [rawFocusedAgentIds, channelMembers]);

  const toggleFocusedAgent = useCallback((agentId: string) => {
    setRawFocusedAgentIds(prev => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  }, []);

  const visibleFiltered = useMemo(() => {
    return filtered.filter(m => {
      if (m.is_reasoning && !showReasoning) return false;
      if (m.is_tool_use && !showTools) return false;
      if (focusedAgentIds.size > 0 && !focusedAgentIds.has(m.sender_agent_id)) return false;
      return true;
    });
  }, [filtered, showReasoning, showTools, focusedAgentIds]);

  const rounds = useMemo(() => groupByRoundAndTurn(visibleFiltered), [visibleFiltered]);

  // Round-level virtualization: only rounds near the viewport are mounted, so a
  // run with thousands of entries keeps a small DOM. Round heights vary and are
  // measured dynamically via ``measureElement``.
  const rowVirtualizer = useVirtualizer({
    count: rounds.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: () => 480,
    overscan: 4,
    getItemKey: index => `round-${rounds[index]?.roundNumber ?? index}`,
  });
  const virtualItems = rowVirtualizer.getVirtualItems();

  // The round at the top of the viewport drives the floating "Round N" badge.
  // Derived from the scroll offset, not ``virtualItems[0]``: the virtual window
  // includes ``overscan`` items rendered *above* the viewport, so the first
  // mounted item is several rounds behind what the user is actually reading.
  const scrollOffset = rowVirtualizer.scrollOffset ?? 0;
  const topVisibleItem = virtualItems.find(item => item.end > scrollOffset) ?? virtualItems[0];
  const currentVisibleRound =
    topVisibleItem !== undefined ? (rounds[topVisibleItem.index]?.roundNumber ?? null) : null;

  // Round index for a round number / a message id, so jumps can scroll a
  // possibly-unmounted target into the window before touching the DOM.
  const roundIndexByNumber = useMemo(() => {
    const map = new Map<number, number>();
    rounds.forEach((round, index) => map.set(round.roundNumber, index));
    return map;
  }, [rounds]);

  const roundIndexByMessageId = useMemo(() => {
    const map = new Map<string, number>();
    rounds.forEach((round, index) => {
      for (const turn of round.turns) {
        for (const entry of turn.entries) {
          map.set(entry.message_id, index);
        }
      }
    });
    return map;
  }, [rounds]);

  // Flash (and center) a message once it is mounted. The entry may be off-screen
  // when the jump starts, so retry across a few frames until the virtualizer has
  // mounted its round.
  const flashMessage = useCallback((messageId: string) => {
    let attemptsLeft = 30;
    const attempt = () => {
      const el = messageRefs.current.get(messageId);
      if (el) {
        el.scrollIntoView({ behavior: "instant", block: "center" });
        el.classList.remove("animate-highlight");
        // Force reflow so the animation restarts even if just removed.
        void el.offsetWidth;
        el.classList.add("animate-highlight");
        window.setTimeout(() => el.classList.remove("animate-highlight"), 1500);
        return;
      }
      if (attemptsLeft > 0) {
        attemptsLeft -= 1;
        requestAnimationFrame(attempt);
      }
    };
    requestAnimationFrame(attempt);
  }, []);

  const jumpToMessage = useCallback(
    (messageId: string) => {
      const roundIdx = roundIndexByMessageId.get(messageId);
      if (roundIdx !== undefined) {
        rowVirtualizer.scrollToIndex(roundIdx, { align: "center" });
      }
      flashMessage(messageId);
    },
    [roundIndexByMessageId, rowVirtualizer, flashMessage]
  );

  const jumpToRound = useCallback(
    (roundNumber: number) => {
      const roundIdx = roundIndexByNumber.get(roundNumber);
      if (roundIdx !== undefined) {
        rowVirtualizer.scrollToIndex(roundIdx, { align: "start" });
      }
    },
    [roundIndexByNumber, rowVirtualizer]
  );

  const scrollToBottom = useCallback(() => {
    if (rounds.length > 0) {
      rowVirtualizer.scrollToIndex(rounds.length - 1, { align: "end" });
    }
  }, [rounds.length, rowVirtualizer]);

  // Scroll to the latest round on first mount so the newest messages are shown.
  const didInitialScrollRef = useRef(false);
  useEffect(() => {
    if (didInitialScrollRef.current || rounds.length === 0) {
      return;
    }
    didInitialScrollRef.current = true;
    requestAnimationFrame(() => {
      rowVirtualizer.scrollToIndex(rounds.length - 1, { align: "end" });
    });
  }, [rounds.length, rowVirtualizer]);

  // Scroll to a message flagged for highlight (e.g. from the branches viewer or
  // a fork-point jump). Same round-then-flash path as an explicit jump.
  useEffect(() => {
    if (!highlightedMessageId) {
      return;
    }
    const roundIdx = roundIndexByMessageId.get(highlightedMessageId);
    if (roundIdx !== undefined) {
      rowVirtualizer.scrollToIndex(roundIdx, { align: "center" });
    }
    flashMessage(highlightedMessageId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- highlightNonce forces a re-jump to the same id
  }, [highlightedMessageId, highlightNonce]);

  return (
    <div className="relative flex min-h-0 flex-col overflow-hidden">
      <ChatHeader
        headerName={headerName}
        headerDesc={headerDesc}
        channelMembers={channelMembers}
        focusedAgentIds={focusedAgentIds}
        onToggleFocusedAgent={toggleFocusedAgent}
        agentColorMap={agentColorMap}
        showReasoning={showReasoning}
        onShowReasoningChange={setShowReasoning}
        showTools={showTools}
        onShowToolsChange={setShowTools}
        exportSlot={exportSlot}
      />

      {/* Hide the chat-pane round badge while an agent drawer is open
          (activeInstanceRoundRange !== null). The drawer renders its own
          per-round sticky dividers, and the chat-pane sits behind the
          drawer so the badge would otherwise bleed through over the
          drawer's tabs (system prompt, messages, metrics) showing a
          confusing "Round N" that's tied to the chat-pane's scroll
          position rather than the active agent instance. */}
      {currentVisibleRound !== null && activeInstanceRoundRange === null ? (
        <ChatRoundBadge
          currentVisibleRound={currentVisibleRound}
          sortedRoundNumbers={sortedRoundNumbers}
          onOpenTimeline={setTimelineRound}
          onScrollToRound={jumpToRound}
        />
      ) : null}

      {timelineRound !== null ? (
        <RoundTimelineModal
          roundNumber={timelineRound}
          messages={messagesByRound.get(timelineRound) ?? []}
          scenarioName={scenarioName}
          scenarioExtras={scenarioExtras}
          roundEnding={endingByRound.get(timelineRound) ?? null}
          onClose={() => setTimelineRound(null)}
        />
      ) : null}

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-0 py-1"
        onScroll={handleScroll}
      >
        <div
          ref={innerContentRef}
          className="relative"
          style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
        >
          <ConnectionWires
            pairs={notificationPairs}
            messageRefs={messageRefs}
            containerRef={innerContentRef}
            hoveredCallId={hoveredCallId}
          />
          {virtualItems.map(virtualItem => {
            const round = rounds[virtualItem.index];
            if (round === undefined) {
              return null;
            }
            const roundIdx = virtualItem.index;
            return (
              <div
                key={virtualItem.key}
                data-index={virtualItem.index}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              >
                {scenarioMarkers
                  .filter(marker => marker.roundNumber === round.roundNumber)
                  .map(marker => (
                    <ScenarioMarkerDivider key={marker.id} marker={marker} />
                  ))}
                {replaceAgentSource !== null &&
                round.roundNumber === replaceAgentSource.round_start ? (
                  <div
                    id="replace-agent-divider"
                    className="mx-4 my-4 rounded-md border-2 border-dashed border-sky-400/80 bg-sky-50 px-4 py-3 dark:border-sky-600/70 dark:bg-sky-950/50"
                  >
                    <div className="flex items-center justify-center gap-2 text-sky-800 dark:text-sky-200">
                      <UserCog className="h-4 w-4" />
                      <span className="text-sm font-semibold">
                        {replaceAgentSource.replaced_agent_id} replaced with{" "}
                        {replaceAgentSource.replacement_model}
                      </span>
                    </div>
                    <div className="mt-1 text-center text-[11px] text-sky-700/80 dark:text-sky-300/80">
                      Round {round.roundNumber} begins with the replacement on a fresh history.
                      Other agents continue from their full reconstructed history.
                    </div>
                  </div>
                ) : null}
                {crossRunReplaceAgentSource !== null &&
                round.roundNumber === crossRunReplaceAgentSource.round_start ? (
                  <div
                    id="cross-run-replace-agent-divider"
                    className="mx-4 my-4 rounded-md border-2 border-dashed border-violet-400/80 bg-violet-50 px-4 py-3 dark:border-violet-600/70 dark:bg-violet-950/50"
                  >
                    <div className="flex items-center justify-center gap-2 text-violet-800 dark:text-violet-200">
                      <UserCog className="h-4 w-4" />
                      <span className="text-sm font-semibold">
                        {crossRunReplaceAgentSource.replaced_agent_id} imported from{" "}
                        <Link
                          href={groupPath(`/runs/${crossRunReplaceAgentSource.source_b_run_id}`)}
                          className="underline-offset-2 hover:underline"
                        >
                          {crossRunReplaceAgentSource.source_b_run_id}
                        </Link>
                      </span>
                    </div>
                    <div className="mt-1 text-center text-[11px] text-violet-700/80 dark:text-violet-300/80">
                      Round {round.roundNumber} begins with the imported agent carrying its full
                      history from source B; this timeline derives from source A{" "}
                      <Link
                        href={groupPath(`/runs/${crossRunReplaceAgentSource.source_a_run_id}`)}
                        className="underline-offset-2 hover:underline"
                      >
                        {crossRunReplaceAgentSource.source_a_run_id}
                      </Link>
                      . Other agents continue from this run.
                    </div>
                  </div>
                ) : null}
                {agentSwapDividers
                  .filter(swap => swap.round_number === round.roundNumber)
                  .map(swap => (
                    <button
                      key={swap.post_swap_instance_key}
                      id={`agent-swap-divider-r${swap.round_number}-${swap.agent_id}`}
                      type="button"
                      onClick={() => onSelectAgent(swap.post_swap_instance_key)}
                      className="mx-4 my-4 block w-[calc(100%-2rem)] rounded-md border-2 border-dashed border-indigo-400/80 bg-indigo-50 px-4 py-3 text-left transition-colors hover:bg-indigo-100/70 dark:border-indigo-600/70 dark:bg-indigo-950/50 dark:hover:bg-indigo-900/50"
                    >
                      <div className="flex items-center justify-center gap-2 text-indigo-800 dark:text-indigo-200">
                        <UserCog className="h-4 w-4" />
                        <span className="text-sm font-semibold">
                          {swap.role_name} swapped — {swap.old_model} → {swap.new_model}
                        </span>
                      </div>
                      <div className="mt-1 text-center text-[11px] text-indigo-700/80 dark:text-indigo-300/80">
                        Round {round.roundNumber} begins with reconstructed history. Click to open
                        Gen {swap.generation}.
                      </div>
                    </button>
                  ))}
                {contextCompactionMarkers
                  .filter(marker => marker.round_number === round.roundNumber)
                  .map(marker => (
                    <div
                      key={`context-compaction-r${marker.round_number}-${marker.agent_id}`}
                      id={`context-compaction-divider-r${marker.round_number}-${marker.agent_id}`}
                      className="mx-4 my-4 rounded-md border-2 border-dashed border-amber-400/80 bg-amber-50 px-4 py-3 dark:border-amber-600/70 dark:bg-amber-950/50"
                    >
                      <div className="flex items-center justify-center gap-2 text-amber-800 dark:text-amber-200">
                        <Archive className="h-4 w-4" />
                        <span className="text-sm font-semibold">
                          {marker.role_name} — context compacted ({marker.provider_name})
                        </span>
                      </div>
                      <div className="mt-1 text-center text-[11px] text-amber-700/80 dark:text-amber-300/80">
                        {marker.summary_text
                          ? `Message history summarized into ${marker.summary_char_count.toLocaleString()} characters at round ${round.roundNumber}.`
                          : `Message history compacted at round ${round.roundNumber}. ${marker.provider_name} stores the summary encrypted server-side, so its text is not available.`}
                      </div>
                      {marker.summary_text ? (
                        <details className="mt-2 text-[11px] text-amber-800 dark:text-amber-200">
                          <summary className="cursor-pointer text-center font-medium">
                            Show summary
                          </summary>
                          <p className="mt-2 whitespace-pre-wrap rounded bg-amber-100/60 p-2 dark:bg-amber-900/30">
                            {marker.summary_text}
                          </p>
                        </details>
                      ) : null}
                    </div>
                  ))}
                <div
                  data-round-marker={round.roundNumber}
                  className="flex items-center gap-2.5 px-4 pb-1.5 pt-3.5"
                >
                  <div className="h-px flex-1 bg-border" />
                  <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                    Round {round.roundNumber}
                  </span>
                  <div className="h-px flex-1 bg-border" />
                </div>

                <RoundInjectionRow
                  injections={(injectionsByRound.get(round.roundNumber) ?? []).filter(
                    i => focusedAgentIds.size === 0 || focusedAgentIds.has(i.agent_id)
                  )}
                  roleNameForAgent={roleNameForAgent}
                />

                {round.turns.map((turn, turnIdx) => {
                  const agent = agentMap.get(turn.agentId);
                  const color = agentColorMap.get(turn.agentId);
                  // Prefer a display name only when it differs from the agent_id:
                  // legacy runs (recorded before sender_display_name existed) backfill
                  // it with the raw agent_id, so fall through to the role name there.
                  // Scenarios that rotate identity behind one agent_id still get their
                  // distinct display name.
                  const distinctDisplayName = turn.entries.find(
                    e => e.sender_display_name && e.sender_display_name !== turn.agentId
                  )?.sender_display_name;
                  const turnDisplayName = distinctDisplayName ?? agent?.role_name ?? turn.agentId;

                  const isPreResume =
                    resumeCutoffTimestamp !== null && turn.timestamp < resumeCutoffTimestamp;
                  return (
                    <div
                      key={`${roundIdx}-${turnIdx}-${turn.agentId}`}
                      className={cn(
                        "flex gap-2.5 px-4 py-1 transition-colors hover:bg-muted/50",
                        isPreResume && "opacity-50"
                      )}
                    >
                      <div className="flex w-7 shrink-0 flex-col items-start">
                        <button
                          aria-label={`Open agent ${turnDisplayName}`}
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
                            {turnDisplayName}
                          </button>
                          <span className="text-[10px] text-muted-foreground">
                            {formatTime(turn.timestamp)}
                          </span>
                        </div>
                        {turn.entries.map((entry, entryIdx) => {
                          const entryChColor = channelColorMap.get(entry.channel_id);
                          const displayText = entry.text;

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
                              onMouseLeave={
                                hasLinkedPair ? () => setHoveredCallId(null) : undefined
                              }
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
                              ) : (
                                <>
                                  {displayText ? (
                                    <ProseMarkdown
                                      className={cn(
                                        !entry.is_reasoning && "text-foreground",
                                        "[&_em]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[11px]"
                                      )}
                                    >
                                      {displayText.replace(/_/g, "\\_")}
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
                                </>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}

                <RoundOutcomeRow
                  results={resultsByRound.get(round.roundNumber) ?? []}
                  trigger={endingByRound.get(round.roundNumber)?.trigger ?? null}
                />
              </div>
            );
          })}
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
      judgeMetadata={entry.judge_metadata}
      toolMetadata={entry.tool_metadata}
    />
  );
}
