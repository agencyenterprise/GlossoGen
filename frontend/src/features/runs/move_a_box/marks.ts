/**
 * The marks and colors move_a_box's round-detail panel draws with.
 *
 * One color per operator, validated for both the light and the dark chart
 * surface. Identity never rests on color alone: every operator is direct-labeled
 * beside its own floor and at the end of its temperature line.
 *
 * Each haul method wears its own mark, so a crate carried the same way every
 * step reads as one repeated mark and a crate whose method changes reads as a
 * change. That is the behaviour the channel would show.
 */

/** Stroke color per operator, in the order the run registers them. */
export const OPERATOR_COLORS = ["#3b82f6", "#ea580c"] as const;

/** The mark drawn at a step carried by each haul method. */
export interface MethodMark {
  shape: "circle" | "square";
  filled: boolean;
}

export const METHOD_MARKS: Record<string, MethodMark> = {
  cart: { shape: "circle", filled: true },
  sled: { shape: "circle", filled: false },
  drag: { shape: "square", filled: true },
};

/** The actions that spend a step without moving the crate. */
export const IN_PLACE_ACTIONS = ["stand_by", "pack_ice"] as const;

/** An action and what it does to the reading, e.g. ``cart +1``, from the run's own numbers. */
export function deltaLabel(action: string, deltas: Record<string, number>): string {
  const name = action.replace("_", " ");
  const delta = deltas[action];
  if (delta === undefined) return name;
  if (delta > 0) return `${name} +${delta}`;
  return `${name} ${delta}`;
}

/** The color for the operator at ``index`` in the round's operator list. */
export function operatorColor(index: number): string {
  return OPERATOR_COLORS[index % OPERATOR_COLORS.length]!;
}

/** The trailing part of an agent id, for a direct label beside a mark. */
export function shortAgentName(agentId: string): string {
  const parts = agentId.split("_");
  const last = parts[parts.length - 1];
  if (last === undefined || last.length === 0) return agentId;
  return last.toUpperCase();
}
