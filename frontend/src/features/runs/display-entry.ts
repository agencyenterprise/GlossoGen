import type { ReactNode } from "react";
import type { components } from "@/types/api.gen";
import { parseNotificationResult, TOOL_NAME_READ_NOTIFICATIONS } from "./notification-display";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type ToolUseEntry = components["schemas"]["ToolUseEntry"];
type AgentRunCycleFailedEntry = components["schemas"]["AgentRunCycleFailedEntry"];
type ScenarioExtras = NonNullable<components["schemas"]["RunDetailResponse"]["scenario_extras"]>;

/** Generic LLM-judge ground truth for a single judged action tool call.
 *
 *  Scenarios whose executor submits a free-text action scored by an LLM
 *  judge surface the same three facts per call, normalized backend-side into
 *  the uniform ``judge_ground_truth_by_call_id`` map on their
 *  ``scenario_extras``. Bespoke per-scenario verdicts (e.g. the container-yard
 *  move verdict) render through the scenario plug-in's ``renderToolMetadata``
 *  hook instead, carried on ``DisplayEntry.tool_metadata``. */
export type JudgeGroundTruthMetadata = components["schemas"]["JudgeGroundTruthMetadata"];

/** Extract the per-call LLM-judge ground truth from a run's
 *  ``scenario_extras``. Every judged-action scenario exposes the same
 *  ``judge_ground_truth_by_call_id`` field (built by its backend run-detail
 *  extension); scenarios with no judged action omit it, yielding an empty map. */
export function judgeMetadataFromExtras(
  extras: ScenarioExtras | null
): Record<string, JudgeGroundTruthMetadata> {
  if (extras !== null && "judge_ground_truth_by_call_id" in extras) {
    return extras.judge_ground_truth_by_call_id;
  }
  return {};
}

/** Unified display type used by ChatPane and AgentDrawer to render
 *  channel messages, reasoning entries, tool uses, and run-cycle failures
 *  in a single timeline. */
export interface DisplayEntry {
  message_id: string;
  channel_id: string;
  channel_ids: string[];
  sender_agent_id: string;
  /** Display name resolved at message-send time. Populated server-side for
   *  channel messages so historical messages from a rotating-identity slot
   *  render under the name the slot held in the message's round. Empty string
   *  on reasoning, tool, and run-cycle failure entries — callers fall back to
   *  the agent's static role name. */
  sender_display_name: string;
  text: string;
  timestamp: string;
  round_number: number;
  is_reasoning: boolean;
  is_tool_use: boolean;
  /** True when this entry renders the parsed notification response paired
   *  with a prior read_notifications tool-call entry sharing the same call_id. */
  is_notification_result: boolean;
  /** True when this entry renders an AgentRunCycleFailed event (content filter
   *  refusal, HTTP error, unexpected model behavior, etc.). */
  is_run_cycle_failure: boolean;
  /** Character count of the message text — only meaningful for channel messages. */
  character_count: number;
  /** Tool use fields — only populated when is_tool_use or is_notification_result is true. */
  tool_name: string;
  tool_arguments: Record<string, unknown>;
  tool_result: string | null;
  /** Call id linking a read_notifications tool call to its notification result entry. */
  call_id: string;
  /** Paired entry's message_id for click-to-scroll (empty when there is no pair). */
  paired_message_id: string;
  judge_metadata: JudgeGroundTruthMetadata | null;
  /** Scenario-specific supplementary content for this tool call, produced by
   *  the scenario plug-in's ``renderToolMetadata`` hook. Null for tools and
   *  scenarios with nothing to add (e.g. the container-yard move verdict). */
  tool_metadata: ReactNode;
  /** Exception class name for run-cycle failure entries (empty otherwise). */
  error_type: string;
  /** Retry-loop cycle index for run-cycle failure entries (0 otherwise). */
  cycle: number;
}

const EMPTY_ENTRY_DEFAULTS = {
  sender_display_name: "",
  is_reasoning: false,
  is_tool_use: false,
  is_notification_result: false,
  is_run_cycle_failure: false,
  character_count: 0,
  tool_name: "",
  tool_arguments: {} as Record<string, unknown>,
  tool_result: null as string | null,
  call_id: "",
  paired_message_id: "",
  judge_metadata: null as JudgeGroundTruthMetadata | null,
  tool_metadata: null as ReactNode,
  error_type: "",
  cycle: 0,
};

/** Merge channel messages, reasoning entries, tool uses, and run-cycle
 *  failures into a single sorted array.
 *
 *  ``judgeMetadataByCallId`` carries the generic LLM-judge ground truth
 *  keyed by tool ``call_id`` (empty for scenarios with no judged action).
 *  ``toolMetadataByCallId`` carries scenario-specific supplementary tool-call
 *  content pre-rendered by the scenario plug-in's ``renderToolMetadata`` hook,
 *  keyed by tool ``call_id`` (empty for scenarios/tools with nothing to add).
 *  Both are plumbed in by the run-detail page from
 *  ``RunDetailResponse.scenario_extras`` and the live SSE stream. */
export function mergeEntries(
  messages: ChannelMessage[],
  reasoning: ReasoningEntry[],
  toolUse: ToolUseEntry[],
  runCycleFailures: AgentRunCycleFailedEntry[],
  judgeMetadataByCallId: Record<string, JudgeGroundTruthMetadata>,
  toolMetadataByCallId: Record<string, ReactNode>
): DisplayEntry[] {
  const channelEntries: DisplayEntry[] = messages.map(m => ({
    ...EMPTY_ENTRY_DEFAULTS,
    message_id: m.message_id,
    channel_id: m.channel_id,
    channel_ids: [m.channel_id],
    sender_agent_id: m.sender_agent_id,
    sender_display_name: m.sender_display_name,
    text: m.text,
    timestamp: m.timestamp,
    round_number: m.round_number,
    character_count: m.text.length,
  }));

  const reasoningEntries: DisplayEntry[] = reasoning.map(r => ({
    ...EMPTY_ENTRY_DEFAULTS,
    message_id: r.message_id,
    channel_id: "",
    channel_ids: r.channel_ids,
    sender_agent_id: r.sender_agent_id,
    text: r.text,
    timestamp: r.timestamp,
    round_number: r.round_number,
    is_reasoning: true,
  }));

  const failureEntries: DisplayEntry[] = runCycleFailures.map(f => ({
    ...EMPTY_ENTRY_DEFAULTS,
    message_id: f.message_id,
    channel_id: "",
    channel_ids: [],
    sender_agent_id: f.agent_id,
    text: f.message,
    timestamp: f.timestamp,
    round_number: f.round_number,
    is_run_cycle_failure: true,
    error_type: f.error_type,
    cycle: f.cycle,
  }));

  const toolEntries: DisplayEntry[] = [];
  for (const t of toolUse) {
    const split = shouldSplitNotification(t);
    const callMessageId = t.message_id;
    const resultMessageId = `${t.message_id}-result`;
    toolEntries.push({
      ...EMPTY_ENTRY_DEFAULTS,
      message_id: callMessageId,
      channel_id: "",
      channel_ids: [],
      sender_agent_id: t.sender_agent_id,
      text: "",
      timestamp: t.timestamp,
      round_number: t.round_number,
      is_tool_use: true,
      tool_name: t.tool_name,
      tool_arguments: t.arguments,
      // When splitting, hide the result from the call pill — the result
      // renders in its own entry at its own timestamp.
      tool_result: split ? null : t.result,
      call_id: t.call_id,
      paired_message_id: split ? resultMessageId : "",
      judge_metadata: judgeMetadataByCallId[t.call_id] ?? null,
      tool_metadata: toolMetadataByCallId[t.call_id] ?? null,
    });
    if (split && t.result_timestamp !== null) {
      toolEntries.push({
        ...EMPTY_ENTRY_DEFAULTS,
        message_id: resultMessageId,
        channel_id: "",
        channel_ids: [],
        sender_agent_id: t.sender_agent_id,
        text: "",
        timestamp: t.result_timestamp,
        round_number: t.result_round_number ?? t.round_number,
        is_notification_result: true,
        tool_name: t.tool_name,
        tool_arguments: t.arguments,
        tool_result: t.result,
        call_id: t.call_id,
        paired_message_id: callMessageId,
      });
    }
  }

  // Sort priority for entries at the same timestamp:
  // channel messages (0) → tool use / notification result (1) → reasoning
  // or run-cycle failure (2).
  // Tool results (e.g. read_notifications) provide context that reasoning
  // reacts to, so they should appear before reasoning from the same LLM response.
  function sortRank(e: DisplayEntry): number {
    if (e.is_reasoning || e.is_run_cycle_failure) return 2;
    if (e.is_tool_use || e.is_notification_result) return 1;
    return 0;
  }

  return [...channelEntries, ...reasoningEntries, ...toolEntries, ...failureEntries].sort(
    (a, b) => {
      if (a.round_number !== b.round_number) {
        return a.round_number - b.round_number;
      }
      const ts = a.timestamp.localeCompare(b.timestamp);
      if (ts !== 0) return ts;
      return sortRank(a) - sortRank(b);
    }
  );
}

/** True when a read_notifications tool entry has a parseable result and a
 *  result_timestamp, so the call pill and the notification chip can be
 *  rendered as two chronologically distinct entries linked by call_id. */
function shouldSplitNotification(t: ToolUseEntry): boolean {
  if (t.tool_name !== TOOL_NAME_READ_NOTIFICATIONS) return false;
  if (t.result_timestamp === null) return false;
  return parseNotificationResult(t.result) !== null;
}
