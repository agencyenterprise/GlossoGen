import type { components } from "@/types/api.gen";

type ChannelMessage = components["schemas"]["ChannelMessage"];
type ReasoningEntry = components["schemas"]["ReasoningEntry"];
type ToolUseEntry = components["schemas"]["ToolUseEntry"];

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
  /** Tool use fields — only populated when is_tool_use is true. */
  tool_name: string;
  tool_arguments: Record<string, unknown>;
  tool_result: string | null;
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

    tool_name: "",
    tool_arguments: {},
    tool_result: null,
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

    tool_name: "",
    tool_arguments: {},
    tool_result: null,
  }));

  const toolEntries: DisplayEntry[] = toolUse.map(t => ({
    message_id: t.message_id,
    channel_id: "",
    channel_ids: [],
    sender_agent_id: t.sender_agent_id,
    text: "",
    timestamp: t.timestamp,
    round_number: t.round_number,
    is_reasoning: false,
    is_tool_use: true,

    tool_name: t.tool_name,
    tool_arguments: t.arguments,
    tool_result: t.result,
  }));

  return [...channelEntries, ...reasoningEntries, ...toolEntries].sort((a, b) =>
    a.timestamp.localeCompare(b.timestamp)
  );
}
