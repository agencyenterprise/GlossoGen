"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Archive, ChevronDown, UserCog } from "lucide-react";
import Link from "next/link";
import type { components } from "@/types/api.gen";
import { useGroupPath } from "@/features/auth/group-context";
import type { AgentColor } from "./agent-colors";
import type { DisplayEntry } from "./display-entry";
import { buildChatRows } from "./chat-rows";
import { humanize } from "./format";
import { RoundTimelineModal } from "./round-timeline-modal";
import { RoundInjectionRow, RoundOutcomeRow } from "./round-event-row";
import type { ScenarioTimelineMarker } from "./scenario-plugin";
import { ScenarioMarkerDivider } from "./scenario-timeline-marker";
import { ChatEntryRow } from "./chat-entry-row";
import { ChatHeader } from "./chat-header";
import { ChatRoundBadge } from "./chat-round-badge";
import { cleanToolName, useToolVisibility } from "./tool-visibility";
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
  /**
   * Divider to jump to, from one of the floating jump-to buttons. Entries are
   * virtualized, so the target element is usually not mounted when the button is
   * clicked — its row has to be scrolled to first. That is why this carries a
   * round number and not just an element id.
   */
  dividerJumpTarget: DividerJumpTarget | null;
  /** Bumped per request so clicking the same button twice jumps again. */
  dividerJumpNonce: number;
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
  /** Ids of the channels the scenario scores, from `get_primary_channels()` on
   *  the backend. The round-detail modal shows messages on these. */
  primaryChannelIds: string[];
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

/** A divider the run viewer can scroll to, identified by element and round. */
export interface DividerJumpTarget {
  elementId: string;
  roundNumber: number;
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
  /** The readable summary, or "" when none was returned (OpenAI keeps it encrypted; agent CLIs keep theirs). */
  summary_text: string;
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
  dividerJumpTarget,
  dividerJumpNonce,
  highlightNonce,
  forkPointMessageId,
  scenarioMarkers,
  replaceAgentSource,
  crossRunReplaceAgentSource,
  scenarioName,
  primaryChannelIds,
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

  // Observe the virtual spacer after dynamic row measurements. DOM mutations
  // alone miss changes to its height and fire while offscreen rows mount.
  useEffect(() => {
    const el = scrollContainerRef.current;
    const content = innerContentRef.current;
    if (!el || !content) return undefined;

    const observer = new ResizeObserver(() => {
      if (!isAtBottomRef.current) return;
      if (el.scrollHeight <= prevScrollHeightRef.current) return;
      prevScrollHeightRef.current = el.scrollHeight;
      el.scrollTop = el.scrollHeight;
    });

    observer.observe(content);
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
  // Derived from the entries this view can show, so the control disappears in a
  // channel view: tool calls carry no channel and only surface under "all
  // activity". Toggles live in the hook, so they survive switching views.
  const toolVisibility = useToolVisibility(filtered);

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

  const isToolVisible = toolVisibility.isVisible;
  const visibleFiltered = useMemo(() => {
    return filtered.filter(m => {
      if (m.is_reasoning && !showReasoning) return false;
      if (m.is_tool_use || m.is_notification_result) {
        if (!isToolVisible(cleanToolName(m.tool_name))) return false;
      }
      if (focusedAgentIds.size > 0 && !focusedAgentIds.has(m.sender_agent_id)) return false;
      return true;
    });
  }, [filtered, showReasoning, isToolVisible, focusedAgentIds]);

  // Wires are drawn between a read_notifications call pill and its parsed
  // response, so they follow what the tool filter left on screen.
  const notificationPairs = useMemo(() => {
    const out: Array<{ callMessageId: string; resultMessageId: string; callId: string }> = [];
    for (const e of visibleFiltered) {
      if (e.is_notification_result && e.paired_message_id !== "") {
        out.push({
          callMessageId: e.paired_message_id,
          resultMessageId: e.message_id,
          callId: e.call_id,
        });
      }
    }
    return out;
  }, [visibleFiltered]);

  const { rows, rowIndexByRound, rowIndexByMessage } = useMemo(
    () => buildChatRows(visibleFiltered),
    [visibleFiltered]
  );
  const getItemKey = useCallback((index: number) => rows[index]?.key ?? index, [rows]);

  // Bound mounted activity by viewport size, even when a single round or turn
  // contains thousands of entries. Expanded content is measured dynamically.
  // eslint-disable-next-line react-hooks/incompatible-library -- useVirtualizer returns uncacheable functions
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollContainerRef.current,
    estimateSize: index => (rows[index]?.kind === "entry" ? 100 : 80),
    overscan: 6,
    getItemKey,
    useFlushSync: false,
  });
  const virtualItems = rowVirtualizer.getVirtualItems();
  const scrollOffset = rowVirtualizer.scrollOffset ?? 0;
  const topVisibleItem = virtualItems.find(item => item.end > scrollOffset) ?? virtualItems[0];
  const currentVisibleRound =
    topVisibleItem !== undefined ? (rows[topVisibleItem.index]?.roundNumber ?? null) : null;

  const jumpFrameRef = useRef<number | null>(null);
  const highlightTimerRef = useRef<number | null>(null);
  const highlightedElementRef = useRef<HTMLElement | null>(null);
  const cancelJump = useCallback(() => {
    if (jumpFrameRef.current !== null) cancelAnimationFrame(jumpFrameRef.current);
    if (highlightTimerRef.current !== null) window.clearTimeout(highlightTimerRef.current);
    highlightedElementRef.current?.classList.remove("animate-highlight");
    highlightedElementRef.current = null;
    jumpFrameRef.current = null;
    highlightTimerRef.current = null;
  }, []);
  useEffect(() => cancelJump, [cancelJump]);

  // Scroll to the exact virtual row, then highlight after it mounts. Cancel an
  // older jump when another starts or the chat unmounts.
  const jumpToRow = useCallback(
    (index: number, findElement?: () => HTMLElement | null | undefined) => {
      cancelJump();
      isAtBottomRef.current = false;
      rowVirtualizer.scrollToIndex(index, { align: findElement ? "center" : "start" });
      if (!findElement) return;
      let attemptsLeft = 60;
      const settle = () => {
        const el = findElement();
        if (el) {
          el.scrollIntoView({ behavior: "instant", block: "center" });
          el.classList.remove("animate-highlight");
          void el.offsetWidth;
          el.classList.add("animate-highlight");
          highlightedElementRef.current = el;
          highlightTimerRef.current = window.setTimeout(() => {
            el.classList.remove("animate-highlight");
            highlightedElementRef.current = null;
            highlightTimerRef.current = null;
          }, 1500);
          jumpFrameRef.current = null;
          return;
        }
        if (attemptsLeft-- > 0) {
          rowVirtualizer.scrollToIndex(index, { align: "center" });
          jumpFrameRef.current = requestAnimationFrame(settle);
        }
      };
      jumpFrameRef.current = requestAnimationFrame(settle);
    },
    [cancelJump, rowVirtualizer]
  );

  const jumpToMessage = useCallback(
    (messageId: string) => {
      const index = rowIndexByMessage.get(messageId);
      if (index !== undefined) jumpToRow(index, () => messageRefs.current.get(messageId));
    },
    [rowIndexByMessage, jumpToRow]
  );

  const jumpToRound = useCallback(
    (roundNumber: number) => {
      const index = rowIndexByRound.get(roundNumber);
      if (index !== undefined) jumpToRow(index);
    },
    [rowIndexByRound, jumpToRow]
  );

  const scrollToBottom = useCallback(() => {
    cancelJump();
    isAtBottomRef.current = true;
    if (rows.length > 0) rowVirtualizer.scrollToIndex(rows.length - 1, { align: "end" });
  }, [rows.length, rowVirtualizer, cancelJump]);

  const didInitialScrollRef = useRef(false);
  useEffect(() => {
    if (didInitialScrollRef.current || rows.length === 0) return;
    if (highlightedMessageId || dividerJumpTarget) {
      didInitialScrollRef.current = true;
      return;
    }
    const frame = requestAnimationFrame(() => {
      didInitialScrollRef.current = true;
      scrollToBottom();
    });
    return () => cancelAnimationFrame(frame);
  }, [rows.length, scrollToBottom, highlightedMessageId, dividerJumpTarget]);

  useEffect(() => {
    if (!dividerJumpTarget) return;
    const index = rowIndexByRound.get(dividerJumpTarget.roundNumber);
    if (index !== undefined)
      jumpToRow(index, () => document.getElementById(dividerJumpTarget.elementId));
    // The nonce is an explicit repeat request. Appended live rows must not re-jump.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dividerJumpTarget, dividerJumpNonce]);

  useEffect(() => {
    if (highlightedMessageId) jumpToMessage(highlightedMessageId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only jump on an explicit request
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
        toolVisibility={toolVisibility}
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
          primaryChannelIds={primaryChannelIds}
          scenarioExtras={scenarioExtras}
          roundEnding={endingByRound.get(timelineRound) ?? null}
          onClose={() => setTimelineRound(null)}
        />
      ) : null}

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden px-0 py-1"
        onScroll={handleScroll}
        onWheel={cancelJump}
        onTouchMove={cancelJump}
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
            const row = rows[virtualItem.index];
            if (row === undefined) {
              return null;
            }
            return (
              <div
                key={virtualItem.key}
                data-index={virtualItem.index}
                data-chat-row={row.kind}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              >
                {row.kind === "round-start" ? (
                  <>
                    {scenarioMarkers
                      .filter(marker => marker.roundNumber === row.roundNumber)
                      .map(marker => (
                        <ScenarioMarkerDivider key={marker.id} marker={marker} />
                      ))}
                    {replaceAgentSource !== null &&
                    row.roundNumber === replaceAgentSource.after_round + 1 ? (
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
                          Round {row.roundNumber} begins with the replacement on a fresh history.
                          Other agents continue from their full reconstructed history.
                        </div>
                      </div>
                    ) : null}
                    {crossRunReplaceAgentSource !== null &&
                    row.roundNumber === crossRunReplaceAgentSource.after_round + 1 ? (
                      <div
                        id="cross-run-replace-agent-divider"
                        className="mx-4 my-4 rounded-md border-2 border-dashed border-violet-400/80 bg-violet-50 px-4 py-3 dark:border-violet-600/70 dark:bg-violet-950/50"
                      >
                        <div className="flex items-center justify-center gap-2 text-violet-800 dark:text-violet-200">
                          <UserCog className="h-4 w-4" />
                          <span className="text-sm font-semibold">
                            {crossRunReplaceAgentSource.replaced_agent_id} imported from{" "}
                            <Link
                              href={groupPath(
                                `/runs/${crossRunReplaceAgentSource.source_b_run_id}`
                              )}
                              className="underline-offset-2 hover:underline"
                            >
                              {crossRunReplaceAgentSource.source_b_run_id}
                            </Link>
                          </span>
                        </div>
                        <div className="mt-1 text-center text-[11px] text-violet-700/80 dark:text-violet-300/80">
                          Round {row.roundNumber} begins with the imported agent carrying its full
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
                      .filter(swap => swap.round_number === row.roundNumber)
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
                            Round {row.roundNumber} begins with reconstructed history. Click to open
                            Gen {swap.generation}.
                          </div>
                        </button>
                      ))}
                    {contextCompactionMarkers
                      .filter(marker => marker.round_number === row.roundNumber)
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
                              ? `Message history summarized into ${marker.summary_char_count.toLocaleString()} characters at round ${row.roundNumber}.`
                              : `Message history compacted at round ${row.roundNumber}. ${marker.provider_name} did not return the summary's text, so it is not available.`}
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
                      data-round-marker={row.roundNumber}
                      className="flex items-center gap-2.5 px-4 pb-1.5 pt-3.5"
                    >
                      <div className="h-px flex-1 bg-border" />
                      <span className="whitespace-nowrap text-[11px] text-muted-foreground">
                        Round {row.roundNumber}
                      </span>
                      <div className="h-px flex-1 bg-border" />
                    </div>

                    <RoundInjectionRow
                      injections={(injectionsByRound.get(row.roundNumber) ?? []).filter(
                        i => focusedAgentIds.size === 0 || focusedAgentIds.has(i.agent_id)
                      )}
                      roleNameForAgent={roleNameForAgent}
                    />
                  </>
                ) : null}

                {row.kind === "entry" ? (
                  <ChatEntryRow
                    row={row}
                    agent={agentMap.get(row.turn.agentId)}
                    color={agentColorMap.get(row.turn.agentId)}
                    entryChColor={channelColorMap.get(row.entry.channel_id)}
                    isPreResume={
                      resumeCutoffTimestamp !== null && row.turn.timestamp < resumeCutoffTimestamp
                    }
                    showChannelBadge={showChannelBadge}
                    isLinkHovered={
                      row.entry.paired_message_id !== "" && hoveredCallId === row.entry.call_id
                    }
                    forkPointMessageId={forkPointMessageId}
                    messageRefs={messageRefs}
                    onSelectAgent={onSelectAgent}
                    setHoveredCallId={setHoveredCallId}
                    jumpToMessage={jumpToMessage}
                  />
                ) : null}

                {row.kind === "round-end" ? (
                  <RoundOutcomeRow
                    results={resultsByRound.get(row.roundNumber) ?? []}
                    trigger={endingByRound.get(row.roundNumber)?.trigger ?? null}
                  />
                ) : null}
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
