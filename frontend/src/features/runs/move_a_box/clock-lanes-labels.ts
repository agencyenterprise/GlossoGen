/**
 * The words and numbers the move_a_box clock lanes print.
 *
 * Every time here is virtual seconds since the round started, the figure the
 * depot readout showed the operators. The lanes draw the spans; this module
 * says what an operator was doing at a given second, how its round split
 * between thinking, acting and waiting, and where the axis ticks go.
 */

import type { components } from "@/types/api.gen";

type MoveABoxClockLane = components["schemas"]["MoveABoxClockLane"];
type MoveABoxActionSpan = components["schemas"]["MoveABoxActionSpan"];
type MoveABoxWaitSpan = components["schemas"]["MoveABoxWaitSpan"];

/** Two times closer than this are one instant. */
const SAME_INSTANT_S = 1e-6;

/** Seconds with one decimal, the precision the clock's latency model gives. */
export function seconds(value: number): string {
  return `${value.toFixed(1)} s`;
}

const DIRECTION_GLYPHS: Record<string, string> = {
  left: "←",
  right: "→",
  up: "↑",
  down: "↓",
};

/** An arrow for a move's direction, or null for an action that leaves the crate in place. */
export function directionGlyph(direction: string | null): string | null {
  if (direction === null) return null;
  return DIRECTION_GLYPHS[direction] ?? null;
}

/** An action as the operator wrote it, e.g. ``cart ←`` or ``pack ice``. */
export function actionName(span: MoveABoxActionSpan): string {
  const name = span.action.replace("_", " ");
  const glyph = directionGlyph(span.direction);
  return glyph === null ? name : `${name} ${glyph}`;
}

/** What ended a wait, said from inside it: "until operator_a's action lands at 66.0 s". */
export function waitUntilText(wait: MoveABoxWaitSpan): string {
  const at = seconds(wait.end_s);
  switch (wait.cause) {
    case "other_acted":
      return `until ${wait.woken_by ?? "the other operator"}'s action lands at ${at}`;
    case "timer":
      return `until its ${seconds(wait.timeout_s ?? 0)} timer runs out at ${at}`;
    case "next_round":
      return "until the next round";
    case "released":
      return `until the scenario releases it at ${at}`;
    case "briefing":
      return `until a briefing arrives at ${at}`;
    case "message":
      return `until a message arrives at ${at}`;
    case "run_ended":
      return "until the run ends";
    case "still_waiting":
      return "and still waiting when the log ends";
  }
}

/** What one operator was doing at one second of the round. */
export interface LaneMoment {
  activity: "thinking" | "acting" | "waiting" | "finished" | "none";
  /** The state, said first and loudest. */
  headline: string;
  /** The operator's own words for it, when it gave any. */
  detail: string | null;
}

function covers(span: { start_s: number; end_s: number }, time: number): boolean {
  return span.start_s - SAME_INSTANT_S <= time && time < span.end_s;
}

export function momentAt(lane: MoveABoxClockLane, time: number): LaneMoment {
  const action = lane.actions.find(span => covers(span, time));
  if (action !== undefined) {
    return {
      activity: "acting",
      headline: `${actionName(action)}, lands at ${seconds(action.end_s)}`,
      detail: action.reasoning,
    };
  }
  const thinking = lane.thinking.find(span => covers(span, time));
  if (thinking !== undefined) {
    return {
      activity: "thinking",
      headline: `Thinking: ${thinking.output_tokens} tokens cost ${seconds(thinking.cost_s)}`,
      detail: null,
    };
  }
  const wait = lane.waits.find(span => covers(span, time));
  if (wait !== undefined) {
    return { activity: "waiting", headline: `Waiting ${waitUntilText(wait)}`, detail: null };
  }
  const finish = lane.finishes.filter(mark => mark.at_s <= time).at(-1);
  if (finish !== undefined) {
    const where = finish.bay === null ? "off the bays" : `on bay ${finish.bay}`;
    return { activity: "finished", headline: `Finished ${where}`, detail: finish.reasoning };
  }
  return { activity: "none", headline: "Nothing logged", detail: null };
}

/** How an operator ended the round: where and when it last finished, or that it never did. */
export function finishText(lane: MoveABoxClockLane): string {
  const finish = lane.finishes.at(-1);
  if (finish === undefined) return "Did not finish";
  const where = finish.bay === null ? "off the bays" : `on bay ${finish.bay}`;
  return `Finished ${where} at ${seconds(finish.at_s)}`;
}

/** How much of the round one operator spent on each kind of span, as fractions of it. */
export interface LaneShares {
  thinking: number;
  acting: number;
  waiting: number;
}

function spent(spans: { start_s: number; end_s: number }[]): number {
  return spans.reduce((sum, span) => sum + (span.end_s - span.start_s), 0);
}

export function laneShares(lane: MoveABoxClockLane, duration: number): LaneShares {
  if (duration <= 0) return { thinking: 0, acting: 0, waiting: 0 };
  return {
    thinking: spent(lane.thinking) / duration,
    acting: spent(lane.actions) / duration,
    waiting: spent(lane.waits) / duration,
  };
}

/** A share as a whole percentage. */
export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

/** Steps the axis may count in, in seconds. */
const TICK_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300] as const;

/** The step used when even the longest one would put ticks closer than asked. */
const LONGEST_TICK_STEP = 600;

/** Axis ticks every whole step at least ``minGapPx`` apart, from zero to ``duration``. */
export function clockTicks(duration: number, pxPerSecond: number, minGapPx: number): number[] {
  const step =
    TICK_STEPS.find(candidate => candidate * pxPerSecond >= minGapPx) ?? LONGEST_TICK_STEP;
  const ticks: number[] = [];
  for (let tick = 0; tick <= duration + SAME_INSTANT_S; tick += step) ticks.push(tick);
  return ticks;
}
