export interface AgentColor {
  bg: string;
  fg: string;
  pillBg: string;
  pillFg: string;
}

const PALETTE: AgentColor[] = [
  { bg: "bg-blue-100", fg: "text-blue-800", pillBg: "bg-blue-50", pillFg: "text-blue-700" },
  { bg: "bg-orange-100", fg: "text-orange-800", pillBg: "bg-orange-50", pillFg: "text-orange-700" },
  { bg: "bg-green-100", fg: "text-green-800", pillBg: "bg-green-50", pillFg: "text-green-700" },
  { bg: "bg-purple-100", fg: "text-purple-800", pillBg: "bg-purple-50", pillFg: "text-purple-700" },
  { bg: "bg-stone-100", fg: "text-stone-600", pillBg: "bg-stone-50", pillFg: "text-stone-600" },
  { bg: "bg-rose-100", fg: "text-rose-800", pillBg: "bg-rose-50", pillFg: "text-rose-700" },
  { bg: "bg-cyan-100", fg: "text-cyan-800", pillBg: "bg-cyan-50", pillFg: "text-cyan-700" },
  { bg: "bg-amber-100", fg: "text-amber-800", pillBg: "bg-amber-50", pillFg: "text-amber-700" },
];

const CHANNEL_PILL_COLORS = [
  { bg: "bg-blue-50", fg: "text-blue-700" },
  { bg: "bg-amber-50", fg: "text-amber-700" },
  { bg: "bg-emerald-50", fg: "text-emerald-700" },
  { bg: "bg-rose-50", fg: "text-rose-700" },
];

export function getAgentColor(index: number): AgentColor {
  return PALETTE[index % PALETTE.length]!;
}

export function getChannelPillColor(index: number): { bg: string; fg: string } {
  return CHANNEL_PILL_COLORS[index % CHANNEL_PILL_COLORS.length]!;
}

export function buildAgentColorMap(agentIds: string[]): Map<string, AgentColor> {
  const map = new Map<string, AgentColor>();
  agentIds.forEach((id, i) => {
    map.set(id, getAgentColor(i));
  });
  return map;
}

export function buildChannelColorMap(
  channelIds: string[]
): Map<string, { bg: string; fg: string }> {
  const map = new Map<string, { bg: string; fg: string }>();
  channelIds.forEach((id, i) => {
    map.set(id, getChannelPillColor(i));
  });
  return map;
}
