export interface AgentColor {
  bg: string;
  fg: string;
}

const PALETTE: AgentColor[] = [
  { bg: "bg-blue-100", fg: "text-blue-800" },
  { bg: "bg-orange-100", fg: "text-orange-800" },
  { bg: "bg-green-100", fg: "text-green-800" },
  { bg: "bg-purple-100", fg: "text-purple-800" },
  { bg: "bg-stone-100", fg: "text-stone-600" },
  { bg: "bg-rose-100", fg: "text-rose-800" },
  { bg: "bg-cyan-100", fg: "text-cyan-800" },
  { bg: "bg-amber-100", fg: "text-amber-800" },
];

const CHANNEL_PILL_COLORS: AgentColor[] = [
  { bg: "bg-blue-50", fg: "text-blue-700" },
  { bg: "bg-amber-50", fg: "text-amber-700" },
  { bg: "bg-emerald-50", fg: "text-emerald-700" },
  { bg: "bg-rose-50", fg: "text-rose-700" },
];

export function getAgentColor(index: number): AgentColor {
  return PALETTE[index % PALETTE.length]!;
}

export function getChannelPillColor(index: number): AgentColor {
  return CHANNEL_PILL_COLORS[index % CHANNEL_PILL_COLORS.length]!;
}

export function deriveInitials(roleName: string): string {
  const words = roleName.split(/\s+/);
  if (words.length >= 2) {
    return (words[0]![0]! + words[1]![0]!).toUpperCase();
  }
  return (roleName.slice(0, 2) || "?").toUpperCase();
}

export function buildAgentColorMap(agentIds: string[]): Map<string, AgentColor> {
  const map = new Map<string, AgentColor>();
  agentIds.forEach((id, i) => {
    map.set(id, getAgentColor(i));
  });
  return map;
}

export function buildChannelColorMap(channelIds: string[]): Map<string, AgentColor> {
  const map = new Map<string, AgentColor>();
  channelIds.forEach((id, i) => {
    map.set(id, getChannelPillColor(i));
  });
  return map;
}
