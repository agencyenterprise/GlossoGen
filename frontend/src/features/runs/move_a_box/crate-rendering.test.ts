import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { FloorPlan } from "./floor-plan";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxCrateTrace = components["schemas"]["MoveABoxCrateTrace"];

function crate(slot: number, marking: string, col: number): MoveABoxCrateTrace {
  return {
    crate_id: `operator_a#${slot}`,
    marking,
    slot,
    steps: [
      {
        sequence: slot,
        action: "cart",
        direction: "right",
        cell: { row: 1, col },
        temperature: 21,
        reasoning: null,
      },
    ],
    final_cell: { row: 1, col },
    final_bay: slot,
    final_temperature: 21,
    finished: true,
  };
}

function draw(crates: MoveABoxCrateTrace[]): string {
  const floor: MoveABoxOperatorFloor = {
    agent_id: "operator_a",
    start: { row: 1, col: 1 },
    pallets: [],
    allowed_bays: [1, 2],
    points: 20,
    crates,
  };
  return renderToStaticMarkup(
    createElement(FloorPlan, {
      floor,
      gridSize: 5,
      bays: [
        { row: 1, col: 3 },
        { row: 1, col: 4 },
      ],
      sharedBays: [1],
      color: "#3b82f6",
    })
  );
}

describe("telling one operator's crates apart on its floor", () => {
  it("badges each crate's final square with its slot when there is more than one", () => {
    const svg = draw([crate(1, "CR-1111", 3), crate(2, "CR-2222", 4)]);

    expect(svg).toContain("CR-1111 (crate 1) ended here");
    expect(svg).toContain("CR-2222 (crate 2) ended here");
  });

  it("draws the first crate's path solid and the second dashed", () => {
    const svg = draw([crate(1, "CR-1111", 3), crate(2, "CR-2222", 4)]);
    const polylines = svg.match(/<polyline[^>]*>/g) ?? [];

    expect(polylines).toHaveLength(2);
    expect(polylines[0]).not.toContain("stroke-dasharray");
    expect(polylines[1]).toContain('stroke-dasharray="6 3"');
  });

  it("badges nothing when the operator works one crate, which needs no telling apart", () => {
    const svg = draw([crate(1, "CR-1111", 3)]);

    expect(svg).not.toContain("ended here");
    expect(svg.match(/<polyline[^>]*>/g) ?? []).toHaveLength(1);
  });
});
