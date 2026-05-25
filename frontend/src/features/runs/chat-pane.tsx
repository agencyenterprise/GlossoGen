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
  Check,
  ChevronDown,
  CloudUpload,
  Download,
  Hash,
  Loader2,
  Package,
  RefreshCw,
  UserCog,
  UserPlus,
} from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Tooltip } from "@/shared/components/ui/tooltip";
import { api, downloadAuthenticatedFile } from "@/shared/lib/api-client";
import { splitRunId } from "@/shared/lib/run-id";
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

type AgentDetail = components["schemas"]["AgentDetail"];
type RunDetailResponse = components["schemas"]["RunDetailResponse"];
type ScenarioExtras = NonNullable<RunDetailResponse["scenario_extras"]>;
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
  /** Round at which an agent was replaced via replace-agent (if this run was derived). */
  replaceAgentRoundStart: number | null;
  /** Agent ID that was replaced (only set when replaceAgentRoundStart is set). */
  replaceAgentReplacedAgentId: string | null;
  /** Replacement model identifier (only set when replaceAgentRoundStart is set). */
  replaceAgentReplacementModel: string | null;
  /** Round at which an agent was imported via cross-run replace (if this run was derived). */
  crossRunReplaceRoundStart: number | null;
  /** Agent ID slot filled by the imported agent (only set when crossRunReplaceRoundStart is set). */
  crossRunReplacedAgentId: string | null;
  /** Source A run id (target timeline) (only set when crossRunReplaceRoundStart is set). */
  crossRunSourceARunId: string | null;
  /** Source B run id the imported agent came from (only set when crossRunReplaceRoundStart is set). */
  crossRunSourceBRunId: string | null;
  /** Scenario name, used to dispatch to the scenario plug-in for the round-detail modal. */
  scenarioName: string;
  /** Scenario-specific run extras (e.g. veyru per-round case metadata). Null for scenarios with no extras. */
  scenarioExtras: ScenarioExtras | null;
  /** One entry per completed round describing why its main phase ended. */
  roundEndings: RoundEnding[];
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
  forkPointMessageId,
  swapRoundNumber,
  swappedObserverDisplayNames,
  internJoinRoundNumber,
  internTakeoverRoundNumber,
  replaceAgentRoundStart,
  replaceAgentReplacedAgentId,
  replaceAgentReplacementModel,
  crossRunReplaceRoundStart,
  crossRunReplacedAgentId,
  crossRunSourceARunId,
  crossRunSourceBRunId,
  scenarioName,
  scenarioExtras,
  roundEndings,
  resumeCutoffTimestamp,
  agentSwapDividers,
  activeInstanceRoundRange,
}: ChatPaneProps) {
  const groupPath = useGroupPath();
  const prodUploadStatus = useQuery({
    queryKey: ["prod-upload-status"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/g/{group_slug}/prod-upload/status");
      if (error) throw new Error("Failed to load prod upload status");
      return data;
    },
  });
  const [prodUploadJustSucceeded, setProdUploadJustSucceeded] = useState(false);
  const prodUploadMutation = useMutation({
    mutationFn: async (variables: { force: boolean }) => {
      const { data, error } = await api.POST(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/upload-to-prod",
        {
          params: {
            path: splitRunId(runId),
            query: { force: variables.force },
          },
        }
      );
      if (error) {
        const detail = (error as { detail?: string }).detail ?? "Upload failed";
        throw new Error(detail);
      }
      return data;
    },
    onSuccess: data => {
      if (data.outcome === "already_present") {
        const prodUrl = prodUploadStatus.data?.prod_url ?? "prod";
        if (
          window.confirm(
            `This run is already on ${prodUrl}. Override the existing copy with the local version?`
          )
        ) {
          prodUploadMutation.mutate({ force: true });
        }
        return;
      }
      setProdUploadJustSucceeded(true);
      window.setTimeout(() => setProdUploadJustSucceeded(false), 2000);
    },
    onError: err => {
      window.alert(`Upload to prod failed: ${err instanceof Error ? err.message : String(err)}`);
    },
  });

  const [metadataSyncJustSucceeded, setMetadataSyncJustSucceeded] = useState(false);
  const metadataSyncMutation = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST(
        "/api/g/{group_slug}/runs/{scenario}/{run_dir_name}/sync-metadata-to-prod",
        { params: { path: splitRunId(runId) } }
      );
      if (error) {
        const detail = (error as { detail?: string }).detail ?? "Metadata sync failed";
        throw new Error(detail);
      }
      return data;
    },
    onSuccess: () => {
      setMetadataSyncJustSucceeded(true);
      window.setTimeout(() => setMetadataSyncJustSucceeded(false), 2000);
    },
    onError: err => {
      window.alert(`Metadata sync failed: ${err instanceof Error ? err.message : String(err)}`);
    },
  });

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
  const [showRoundJumper, setShowRoundJumper] = useState(false);
  const roundJumperRef = useRef<HTMLDivElement>(null);

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

  const jumpToRound = useCallback((roundNumber: number) => {
    const el = roundMarkerRefs.current.get(roundNumber);
    if (el) {
      el.scrollIntoView({ behavior: "instant", block: "start" });
    }
    setShowRoundJumper(false);
  }, []);

  // Close the round jumper on outside click or Escape.
  useEffect(() => {
    if (!showRoundJumper) return;
    function handleMouseDown(e: MouseEvent) {
      if (roundJumperRef.current && !roundJumperRef.current.contains(e.target as Node)) {
        setShowRoundJumper(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setShowRoundJumper(false);
    }
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showRoundJumper]);

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
                path: `/api/g/{group_slug}/runs/${runId}/export/pdf`,
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
        <Tooltip label="Export run bundle">
          <button
            aria-label="Export bundle"
            className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => {
              void downloadAuthenticatedFile({
                path: `/api/g/{group_slug}/runs/${runId}/export/bundle`,
                searchParams: new URLSearchParams(),
                fallbackFilename: `${runId.slice(0, 8)}_bundle.tar.gz`,
              });
            }}
          >
            <Package className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
        {prodUploadStatus.data?.configured && (
          <Tooltip label={`Upload to ${prodUploadStatus.data.prod_url}`}>
            <button
              aria-label="Upload to prod"
              disabled={prodUploadMutation.isPending}
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
              onClick={() => {
                if (!window.confirm(`Upload this run to ${prodUploadStatus.data?.prod_url}?`)) {
                  return;
                }
                prodUploadMutation.mutate({ force: false });
              }}
            >
              {prodUploadMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : prodUploadJustSucceeded ? (
                <Check className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <CloudUpload className="h-3.5 w-3.5" />
              )}
            </button>
          </Tooltip>
        )}
        {prodUploadStatus.data?.configured && (
          <Tooltip label={`Sync labels/note/evals to ${prodUploadStatus.data.prod_url}`}>
            <button
              aria-label="Sync metadata to prod"
              disabled={metadataSyncMutation.isPending}
              className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
              onClick={() => {
                if (
                  !window.confirm(
                    `Sync labels, note, and eval report for this run to ${prodUploadStatus.data?.prod_url}?`
                  )
                ) {
                  return;
                }
                metadataSyncMutation.mutate();
              }}
            >
              {metadataSyncMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : metadataSyncJustSucceeded ? (
                <Check className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
            </button>
          </Tooltip>
        )}
      </div>

      {/* Hide the chat-pane round badge while an agent drawer is open
          (activeInstanceRoundRange !== null). The drawer renders its own
          per-round sticky dividers, and the chat-pane sits behind the
          drawer so the badge would otherwise bleed through over the
          drawer's tabs (system prompt, messages, metrics) showing a
          confusing "Round N" that's tied to the chat-pane's scroll
          position rather than the active agent instance. */}
      {currentVisibleRound !== null && activeInstanceRoundRange === null ? (
        <div className="absolute left-1/2 top-12 z-30 flex -translate-x-1/2 items-center gap-1.5">
          <button
            type="button"
            aria-label={`Open round ${currentVisibleRound} timeline`}
            onClick={() => setTimelineRound(currentVisibleRound)}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-border bg-background/90 px-2.5 py-1 text-[11px] font-medium text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
          >
            <Hash className="h-3 w-3" />
            Round {currentVisibleRound}
          </button>
          {sortedRoundNumbers.length > 1 ? (
            <div ref={roundJumperRef} className="relative">
              <Tooltip label="Jump to round">
                <button
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded={showRoundJumper}
                  aria-label="Jump to round"
                  onClick={() => setShowRoundJumper(v => !v)}
                  className="inline-flex cursor-pointer items-center justify-center rounded-full border border-border bg-background/90 p-1 text-muted-foreground shadow-sm backdrop-blur transition-colors hover:border-foreground/30 hover:bg-background hover:text-foreground"
                >
                  <ChevronDown className="h-3 w-3" />
                </button>
              </Tooltip>
              {showRoundJumper ? (
                <div
                  role="listbox"
                  aria-label="Rounds"
                  className="absolute right-0 top-full z-40 mt-1 w-32 overflow-hidden rounded-md border border-border bg-background shadow-lg"
                >
                  <div className="max-h-64 overflow-y-auto py-1">
                    {sortedRoundNumbers.map(n => (
                      <button
                        key={n}
                        type="button"
                        role="option"
                        aria-selected={n === currentVisibleRound}
                        onClick={() => jumpToRound(n)}
                        className={cn(
                          "block w-full px-3 py-1 text-left text-[11px] transition-colors hover:bg-muted",
                          n === currentVisibleRound
                            ? "font-medium text-foreground"
                            : "text-muted-foreground"
                        )}
                      >
                        Round {n}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
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
              {replaceAgentRoundStart !== null && round.roundNumber === replaceAgentRoundStart ? (
                <div
                  id="replace-agent-divider"
                  className="mx-4 my-4 rounded-md border-2 border-dashed border-sky-400/80 bg-sky-50 px-4 py-3 dark:border-sky-600/70 dark:bg-sky-950/50"
                >
                  <div className="flex items-center justify-center gap-2 text-sky-800 dark:text-sky-200">
                    <UserCog className="h-4 w-4" />
                    <span className="text-sm font-semibold">
                      {replaceAgentReplacedAgentId !== null &&
                      replaceAgentReplacementModel !== null ? (
                        <>
                          {replaceAgentReplacedAgentId} replaced with {replaceAgentReplacementModel}
                        </>
                      ) : (
                        <>Agent replaced</>
                      )}
                    </span>
                  </div>
                  <div className="mt-1 text-center text-[11px] text-sky-700/80 dark:text-sky-300/80">
                    Round {round.roundNumber} begins with the replacement on a fresh history. Other
                    agents continue from their full reconstructed history.
                  </div>
                </div>
              ) : null}
              {crossRunReplaceRoundStart !== null &&
              round.roundNumber === crossRunReplaceRoundStart ? (
                <div
                  id="cross-run-replace-agent-divider"
                  className="mx-4 my-4 rounded-md border-2 border-dashed border-violet-400/80 bg-violet-50 px-4 py-3 dark:border-violet-600/70 dark:bg-violet-950/50"
                >
                  <div className="flex items-center justify-center gap-2 text-violet-800 dark:text-violet-200">
                    <UserCog className="h-4 w-4" />
                    <span className="text-sm font-semibold">
                      {crossRunReplacedAgentId !== null && crossRunSourceBRunId !== null ? (
                        <>
                          {crossRunReplacedAgentId} imported from{" "}
                          <Link
                            href={groupPath(`/runs/${crossRunSourceBRunId}`)}
                            className="underline-offset-2 hover:underline"
                          >
                            {crossRunSourceBRunId}
                          </Link>
                        </>
                      ) : (
                        <>Agent imported from another run</>
                      )}
                    </span>
                  </div>
                  <div className="mt-1 text-center text-[11px] text-violet-700/80 dark:text-violet-300/80">
                    Round {round.roundNumber} begins with the imported agent carrying its full
                    history from source B
                    {crossRunSourceARunId !== null ? (
                      <>
                        ; this timeline derives from source A{" "}
                        <Link
                          href={groupPath(`/runs/${crossRunSourceARunId}`)}
                          className="underline-offset-2 hover:underline"
                        >
                          {crossRunSourceARunId}
                        </Link>
                      </>
                    ) : null}
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
                      Round {round.roundNumber} begins with reconstructed history. Click to open Gen{" "}
                      {swap.generation}.
                    </div>
                  </button>
                ))}
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
                const turnDisplayName =
                  turn.entries.find(e => e.sender_display_name)?.sender_display_name ??
                  agent?.role_name ??
                  turn.agentId;

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
      truckMetadata={entry.truck_metadata}
      craneMetadata={entry.crane_metadata}
    />
  );
}
