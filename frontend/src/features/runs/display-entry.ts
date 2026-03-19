import type { components } from "@/types/api.gen";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];

/** Unified display type used by ChatPane and AgentDrawer to render both
 *  channel messages and reasoning entries in a single turn-grouped timeline. */
export interface DisplayEntry {
  message_id: string;
  channel_id: string;
  channel_ids: string[];
  sender_agent_id: string;
  text: string;
  timestamp: string;
  turn_number: number;
  round_number: number;
  is_reasoning: boolean;
}

/** Merge channel messages and reasoning entries into a single sorted array. */
export function mergeEntries(
  messages: ChannelMessage[],
  reasoning: ReasoningEntry[]
): DisplayEntry[] {
  const channelEntries: DisplayEntry[] = messages.map(m => ({
    message_id: m.message_id,
    channel_id: m.channel_id,
    channel_ids: [m.channel_id],
    sender_agent_id: m.sender_agent_id,
    text: m.text,
    timestamp: m.timestamp,
    turn_number: m.turn_number,
    round_number: m.round_number,
    is_reasoning: false,
  }));

  const reasoningEntries: DisplayEntry[] = reasoning.map(r => ({
    message_id: r.message_id,
    channel_id: "",
    channel_ids: r.channel_ids,
    sender_agent_id: r.sender_agent_id,
    text: r.text,
    timestamp: r.timestamp,
    turn_number: r.turn_number,
    round_number: r.round_number,
    is_reasoning: true,
  }));

  return [...channelEntries, ...reasoningEntries].sort((a, b) =>
    a.timestamp.localeCompare(b.timestamp)
  );
}
