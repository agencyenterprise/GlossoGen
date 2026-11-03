import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { FloorPlan } from "./floor-plan";

type MoveABoxOperatorFloor = components["schemas"]["MoveABoxOperatorFloor"];
type MoveABoxCrateTrace = components["schemas"]["MoveABoxCrateTrace"];
type MoveABoxFloorBay = components["schemas"]["MoveABoxFloorBay"];

const NUMBERED_BAYS: MoveABoxFloorBay[] = [
  { number: 1, name: "1,3", label: "1", cell: { row: 1, col: 3 } },
  { number: 2, name: "1,4", label: "2", cell: { row: 1, col: 4 } },
];

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

function draw(crates: MoveABoxCrateTrace[], bays: MoveABoxFloorBay[]): string {
  const floor: MoveABoxOperatorFloor = {
    agent_id: "operator_a",
    start: { row: 1, col: 1 },
    bays,
    pallets: [],
    allowed_bays: [1, 2],
    points: 20,
    crates,
  };
  return renderToStaticMarkup(
    createElement(FloorPlan, {
      floor,
      operatorIndex: 0,
      operatorCount: 2,
      gridSize: 5,
      sharedBays: [1],
      color: "#3b82f6",
    })
  );
}

describe("telling one operator's crates apart on its floor", () => {
  it("badges each crate's final square with its slot when there is more than one", () => {
    const svg = draw([crate(1, "CR-1111", 3), crate(2, "CR-2222", 4)], NUMBERED_BAYS);

    expect(svg).toContain("CR-1111 (crate 1) ended here");
    expect(svg).toContain("CR-2222 (crate 2) ended here");
  });

  it("gives each crate its own colour and its own line style", () => {
    const svg = draw([crate(1, "CR-1111", 3), crate(2, "CR-2222", 4)], NUMBERED_BAYS);
    const polylines = svg.match(/<polyline[^>]*>/g) ?? [];

    expect(polylines).toHaveLength(2);
    const strokes = polylines.map(line => /stroke="([^"]+)"/.exec(line)?.[1]);
    // Every crate has a hue of its own, and the first keeps the operator's.
    expect(strokes[0]).toBe("#3b82f6");
    expect(strokes[1]).not.toBe(strokes[0]);
    expect(polylines[0]).not.toContain("stroke-dasharray");
    expect(polylines[1]).toContain("stroke-dasharray");
  });

  it("badges nothing when the operator works one crate, which needs no telling apart", () => {
    const svg = draw([crate(1, "CR-1111", 3)], NUMBERED_BAYS);

    expect(svg).not.toContain("ended here");
    const polylines = svg.match(/<polyline[^>]*>/g) ?? [];
    expect(polylines).toHaveLength(1);
    expect(polylines[0]).not.toContain("stroke-dasharray");
  });
});

describe("labelling a floor's bays", () => {
  it("draws a symbol-named bay as its symbol and names it in the tooltip", () => {
    const svg = draw(
      [crate(1, "CR-1111", 3)],
      [
        { number: 1, name: "star", label: "\u2605", cell: { row: 1, col: 3 } },
        { number: 2, name: "moon", label: "\u263E", cell: { row: 1, col: 4 } },
      ]
    );

    expect(svg).toContain(">\u2605</text>");
    expect(svg).toContain("Bay \u2605 (star)");
    expect(svg).toContain("Bay \u263E (moon)");
  });
});
