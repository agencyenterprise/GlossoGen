import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { MoveABoxRoundDetailPanel } from "./move-a-box-round-detail-panel";
import { roundFloors, roundMatchLabel, targetMatchLabel, targetStarts } from "./targets";

type MoveABoxRoundFloor = components["schemas"]["MoveABoxRoundFloor"];
type MoveABoxTargetFloor = components["schemas"]["MoveABoxTargetFloor"];
type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];

function side(
  agentId: string,
  start: number,
  sequences: number[],
  points: number
): MoveABoxOperatorFloor {
  return {
    agent_id: agentId,
    start: { row: 1, col: start },
    bays: [{ number: 1, name: "3,3", label: "1", cell: { row: 3, col: 3 } }],
    pallets: [],
    allowed_bays: [1],
    points,
    crates: [
      {
        crate_id: `${agentId}#1`,
        marking: `CR-${agentId}`,
        slot: 1,
        steps: sequences.map(sequence => ({
          sequence,
          action: "cart",
          direction: "right",
          cell: { row: 1, col: start + 1 },
          temperature: 20 + sequence,
          reasoning: null,
        })),
        final_cell: { row: 3, col: 3 },
        final_bay: 1,
        final_temperature: 20 + Math.max(0, ...sequences),
        finished: true,
      },
    ],
  };
}

function target(
  number: number,
  matched: boolean,
  sequences: [number[], number[]]
): MoveABoxTargetFloor {
  return {
    target_number: number,
    shared_bays: [1],
    matched_slots: matched ? [1] : [],
    matched,
    scored: true,
    operators: [
      side("operator_a", number, sequences[0], matched ? 20 : 10),
      side("operator_b", number, sequences[1], matched ? 20 : 10),
    ],
  };
}

const ROUND: MoveABoxRoundFloor = {
  round_number: 1,
  grid_size: 5,
  matched: false,
  targets: [
    target(1, false, [
      [1, 3],
      [2, 4],
    ]),
    target(2, true, [
      [5, 7],
      [6, 8],
    ]),
  ],
};

describe("reading a round of several targets", () => {
  it("joins each crate's steps across targets for the temperature trace", () => {
    const floors = roundFloors(ROUND);

    expect(floors.map(floor => floor.agent_id)).toEqual(["operator_a", "operator_b"]);
    expect(floors[0]!.crates[0]!.steps.map(step => step.sequence)).toEqual([1, 3, 5, 7]);
    expect(floors[1]!.crates[0]!.steps.map(step => step.sequence)).toEqual([2, 4, 6, 8]);
  });

  it("marks each later target half a step before its first action", () => {
    expect(targetStarts(ROUND)).toEqual([{ sequence: 4.5, label: "T2" }]);
  });

  it("names a round by how many of its targets met, and each target by its own result", () => {
    expect(roundMatchLabel(ROUND, 2)).toBe("1 of 2 targets met");
    expect(ROUND.targets.map(targetMatchLabel)).toEqual(["different bays", "same bay"]);
    expect(targetMatchLabel({ ...ROUND.targets[0]!, scored: false })).toBe("in progress");
  });

  it("draws one block per target, each with its heading and floors", () => {
    const html = renderToStaticMarkup(
      createElement(MoveABoxRoundDetailPanel, {
        roundNumber: 1,
        extras: {
          scenario_name: "move_a_box",
          targets_per_round: 2,
          base_temperature: 20,
          temperature_delta: { cart: 1 },
          cases: [ROUND],
        },
      })
    );

    expect(html).toContain("Target 1 of 2");
    expect(html).toContain("Target 2 of 2");
    expect(html).toContain("each crate starts where target 1 left it");
    expect(html).toContain("1 of 2 targets met");
    expect(html).toContain("next target begins");
    expect(html.match(/Floor for operator_a/g)).toHaveLength(2);
  });

  it("keeps a round of one target as a single block with no target headings", () => {
    const single = { ...ROUND, targets: [ROUND.targets[0]!] };
    const html = renderToStaticMarkup(
      createElement(MoveABoxRoundDetailPanel, {
        roundNumber: 1,
        extras: {
          scenario_name: "move_a_box",
          targets_per_round: 1,
          base_temperature: 20,
          temperature_delta: { cart: 1 },
          cases: [single],
        },
      })
    );

    expect(html).not.toContain("Target 1");
    expect(html).toContain("different bays");
    expect(html).not.toContain("next target begins");
  });
});
