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
// One hue per operator, in assignment order. Validated for colour-vision
// deficiency on both surfaces: worst adjacent pair deltaE 10.3 (deutan).
export const OPERATOR_COLORS = [
  "#3b82f6",
  "#ea580c",
  "#9333ea",
  "#16a34a",
  "#0891b2",
  "#db2777",
] as const;

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

/** Dash patterns telling one operator's crates apart. Slot 1 is solid.
 *
 * Slot 2 is dotted rather than long-dashed, because a dotted line reads as a
 * different line at a glance where a long dash still reads as a solid one. */
const CRATE_DASHES = [undefined, undefined, "2 3", "7 3", "9 3 2 3", "1 3"] as const;

export interface CrateStyle {
  color: string;
  dash: string | undefined;
  width: number;
}

/**
 * How one crate is drawn, everywhere it is drawn.
 *
 * Every crate in a round gets a hue of its own, so no two crates share one and
 * no hue turns up on two operators' floors. The first crate of each operator
 * keeps that operator's hue, which is what a single-crate run has always used,
 * and later crates take the hues no operator claimed.
 *
 * The dash carries the same distinction a second time: solid for an operator's
 * first crate, dotted for its second. Two cues for one thing is the point, so
 * an overlap, a colour-vision difference or a greyscale print still separates
 * them. Past six crates the hues repeat and the dash is what is left.
 */
export function crateStyle(args: {
  slot: number;
  operatorIndex: number;
  cratesEach: number;
  operatorCount: number;
}): CrateStyle {
  const index = (args.slot - 1) * args.operatorCount + args.operatorIndex;
  return {
    color: OPERATOR_COLORS[index % OPERATOR_COLORS.length]!,
    dash: args.cratesEach > 1 ? CRATE_DASHES[args.slot % CRATE_DASHES.length] : undefined,
    width: 2,
  };
}
