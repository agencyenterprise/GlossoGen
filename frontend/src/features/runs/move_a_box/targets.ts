/**
 * How the move_a_box panel reads a round of several targets.
 *
 * The payload gives each target its own floors, with each crate's path inside
 * that target. The temperature trace wants each crate's whole round instead, so
 * the targets' steps are joined back up here, and the points where a new target
 * began are kept so the trace can mark them.
 */

import type { components } from "@/types/api.gen";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxRoundFloor = components["schemas"]["MoveABoxRoundFloor"];
type MoveABoxTargetFloor = components["schemas"]["MoveABoxTargetFloor"];

/** Each operator's side of the round, its crates carrying every target's steps in order. */
export function roundFloors(round: MoveABoxRoundFloor): MoveABoxOperatorFloor[] {
  const first = round.targets[0];
  if (first === undefined) return [];
  return first.operators.map((floor, index) => {
    const sides = round.targets.flatMap(target => {
      const side = target.operators[index];
      return side === undefined ? [] : [side];
    });
    const last = sides[sides.length - 1] ?? floor;
    return {
      ...last,
      crates: floor.crates.map(crate => {
        const pieces = sides.flatMap(side =>
          side.crates.filter(candidate => candidate.crate_id === crate.crate_id)
        );
        const latest = pieces[pieces.length - 1] ?? crate;
        return { ...latest, steps: pieces.flatMap(piece => piece.steps) };
      }),
    };
  });
}

/** Where a target after the first begins on the round's action sequence. */
export interface TargetStart {
  sequence: number;
  label: string;
}

/** Each later target's start, half a step before its first action. A target nobody acted in has none. */
export function targetStarts(round: MoveABoxRoundFloor): TargetStart[] {
  return round.targets.slice(1).flatMap(target => {
    const sequences = target.operators.flatMap(side =>
      side.crates.flatMap(crate => crate.steps.map(step => step.sequence))
    );
    if (sequences.length === 0) return [];
    return [{ sequence: Math.min(...sequences) - 0.5, label: `T${target.target_number}` }];
  });
}

/** What a target's badge says about the crates meeting on it.
 *
 * One crate a side has one thing to say. More than one, and the badge names
 * the slots that met, since which ones they were is the whole result. */
export function targetMatchLabel(target: MoveABoxTargetFloor): string {
  if (!target.scored) return "in progress";
  const perOperator = target.operators[0]?.crates.length ?? 1;
  if (perOperator <= 1) return target.matched ? "same bay" : "different bays";
  if (target.matched) return `all ${perOperator} crates met`;
  if (target.matched_slots.length === 0) return `no crate met (0 of ${perOperator})`;
  return `crate ${target.matched_slots.join(" and ")} met, ${
    perOperator - target.matched_slots.length
  } did not`;
}

/** What a round of several targets says about them: how many met, of how many it holds. */
export function roundMatchLabel(round: MoveABoxRoundFloor, targetsPerRound: number): string {
  const met = round.targets.filter(target => target.scored && target.matched).length;
  return `${met} of ${targetsPerRound} targets met`;
}
