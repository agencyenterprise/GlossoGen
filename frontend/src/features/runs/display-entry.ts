import type { components } from "@/types/api.gen";
import { parseNotificationResult, TOOL_NAME_READ_NOTIFICATIONS } from "./notification-display";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type ToolUseEntry = components["schemas"]["ToolUseEntry"];
type VeyruStabilizeMetadata = components["schemas"]["VeyruStabilizeMetadata"];

/** Unified display type used by ChatPane and AgentDrawer to render
 *  channel messages, reasoning entries, and tool uses in a single timeline. */
export interface DisplayEntry {
  message_id: string;
  channel_id: string;
  channel_ids: string[];
  sender_agent_id: string;
  text: string;
  timestamp: string;
  round_number: number;
  is_reasoning: boolean;
  is_tool_use: boolean;
  /** True when this entry renders the parsed notification response paired
   *  with a prior read_notifications tool-call entry sharing the same call_id. */
  is_notification_result: boolean;
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
  stabilize_metadata: VeyruStabilizeMetadata | null;
  /** call_ids of notification pairs whose span covers this entry (call seen,
   *  result not yet). Includes the pair's own endpoints — the call entry and
   *  the result entry each list their own call_id. Used to render the gutter
   *  thread in ChatPane / AgentDrawer. */
  active_pair_call_ids: string[];
  /** Horizontal lane index per active pair. Same length/order as active_pair_call_ids. */
  active_pair_lanes: number[];
}

/** Deterministic hue (0–359) from a call_id so each notification pair gets a
 *  stable, unique color across re-renders. */
export function hueFromCallId(callId: string): number {
  let h = 0;
  for (let i = 0; i < callId.length; i += 1) {
    h = (h * 31 + callId.charCodeAt(i)) >>> 0;
  }
  return h % 360;
}

/** Merge channel messages, reasoning entries, and tool uses into a single sorted array. */
export function mergeEntries(
  messages: ChannelMessage[],
  reasoning: ReasoningEntry[],
  toolUse: ToolUseEntry[]
): DisplayEntry[] {
  const channelEntries: DisplayEntry[] = messages.map(m => ({
    message_id: m.message_id,
    channel_id: m.channel_id,
    channel_ids: [m.channel_id],
    sender_agent_id: m.sender_agent_id,
    text: m.text,
    timestamp: m.timestamp,
    round_number: m.round_number,
    is_reasoning: false,
    is_tool_use: false,
    is_notification_result: false,
    character_count: m.text.length,

    tool_name: "",
    tool_arguments: {},
    tool_result: null,
    call_id: "",
    paired_message_id: "",
    stabilize_metadata: null,
    active_pair_call_ids: [],
    active_pair_lanes: [],
  }));

  const reasoningEntries: DisplayEntry[] = reasoning.map(r => ({
    message_id: r.message_id,
    channel_id: "",
    channel_ids: r.channel_ids,
    sender_agent_id: r.sender_agent_id,
    text: r.text,
    timestamp: r.timestamp,
    round_number: r.round_number,
    is_reasoning: true,
    is_tool_use: false,
    is_notification_result: false,
    character_count: 0,

    tool_name: "",
    tool_arguments: {},
    tool_result: null,
    call_id: "",
    paired_message_id: "",
    stabilize_metadata: null,
    active_pair_call_ids: [],
    active_pair_lanes: [],
  }));

  const toolEntries: DisplayEntry[] = [];
  for (const t of toolUse) {
    const split = shouldSplitNotification(t);
    const callMessageId = t.message_id;
    const resultMessageId = `${t.message_id}-result`;
    toolEntries.push({
      message_id: callMessageId,
      channel_id: "",
      channel_ids: [],
      sender_agent_id: t.sender_agent_id,
      text: "",
      timestamp: t.timestamp,
      round_number: t.round_number,
      is_reasoning: false,
      is_tool_use: true,
      is_notification_result: false,
      character_count: 0,

      tool_name: t.tool_name,
      tool_arguments: t.arguments,
      // When splitting, hide the result from the call pill — the result
      // renders in its own entry at its own timestamp.
      tool_result: split ? null : t.result,
      call_id: t.call_id,
      paired_message_id: split ? resultMessageId : "",
      stabilize_metadata: t.stabilize_metadata ?? null,
      active_pair_call_ids: [],
      active_pair_lanes: [],
    });
    if (split && t.result_timestamp !== null) {
      toolEntries.push({
        message_id: resultMessageId,
        channel_id: "",
        channel_ids: [],
        sender_agent_id: t.sender_agent_id,
        text: "",
        timestamp: t.result_timestamp,
        round_number: t.round_number,
        is_reasoning: false,
        is_tool_use: false,
        is_notification_result: true,
        character_count: 0,

        tool_name: t.tool_name,
        tool_arguments: t.arguments,
        tool_result: t.result,
        call_id: t.call_id,
        paired_message_id: callMessageId,
        stabilize_metadata: null,
        active_pair_call_ids: [],
        active_pair_lanes: [],
      });
    }
  }

  // Sort priority for entries at the same timestamp:
  // channel messages (0) → tool use / notification result (1) → reasoning (2).
  // Tool results (e.g. read_notifications) provide context that reasoning
  // reacts to, so they should appear before reasoning from the same LLM response.
  function sortRank(e: DisplayEntry): number {
    if (e.is_reasoning) return 2;
    if (e.is_tool_use || e.is_notification_result) return 1;
    return 0;
  }

  const sorted = [...channelEntries, ...reasoningEntries, ...toolEntries].sort((a, b) => {
    if (a.round_number !== b.round_number) {
      return a.round_number - b.round_number;
    }
    const ts = a.timestamp.localeCompare(b.timestamp);
    if (ts !== 0) return ts;
    return sortRank(a) - sortRank(b);
  });

  annotateActivePairs(sorted);
  return sorted;
}

/** Populate active_pair_call_ids and active_pair_lanes on each entry so the
 *  ChatPane gutter-thread renderer knows which colored bars to draw in which
 *  lane, with no runtime DOM measurement. Single linear pass: open a lane
 *  when a call entry is seen, close and free it when the matching result
 *  entry is seen. Both endpoints and all intervening entries report the pair
 *  as active (the renderer picks half-height vs full-height based on whether
 *  the current entry is an endpoint for that call_id). */
function annotateActivePairs(entries: DisplayEntry[]): void {
  const openLanes = new Map<string, number>();
  const freeLanes: number[] = [];
  let nextLane = 0;

  for (const entry of entries) {
    // Open a new lane for each notification-splitting call.
    if (entry.is_tool_use && entry.paired_message_id !== "" && entry.call_id !== "") {
      let lane: number;
      if (freeLanes.length > 0) {
        freeLanes.sort((a, b) => a - b);
        lane = freeLanes.shift() as number;
      } else {
        lane = nextLane;
        nextLane += 1;
      }
      openLanes.set(entry.call_id, lane);
    }

    // Snapshot the currently-open pairs onto this entry.
    entry.active_pair_call_ids = Array.from(openLanes.keys());
    entry.active_pair_lanes = entry.active_pair_call_ids.map(id => openLanes.get(id) as number);

    // Close the pair AFTER snapshotting so the result entry still reports it.
    if (entry.is_notification_result && entry.call_id !== "") {
      const lane = openLanes.get(entry.call_id);
      if (lane !== undefined) {
        freeLanes.push(lane);
        openLanes.delete(entry.call_id);
      }
    }
  }
}

/** True when a read_notifications tool entry has a parseable result and a
 *  result_timestamp, so the call pill and the notification chip can be
 *  rendered as two chronologically distinct entries linked by call_id. */
function shouldSplitNotification(t: ToolUseEntry): boolean {
  if (t.tool_name !== TOOL_NAME_READ_NOTIFICATIONS) return false;
  if (t.result_timestamp === null) return false;
  return parseNotificationResult(t.result) !== null;
}
