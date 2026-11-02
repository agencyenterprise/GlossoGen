import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { actionLog, itemLabel } from "./items";
import { SignalGameRoundDetailPanel } from "./signal-game-round-detail-panel";

type SignalGamePlayerSide = components["schemas"]["SignalGamePlayerSide"];
type SignalGameRunExtras = components["schemas"]["SignalGameRunExtras"];

const BLUE_CIRCLE = { colour: "blue", shape: "circle", fill: null };
const RED_STAR = { colour: "red", shape: "star", fill: null };
const RED_CIRCLE = { colour: "red", shape: "circle", fill: null };

/** player_a bounces right and back in one call, then ends; player_b steps down and ends. */
function players(): SignalGamePlayerSide[] {
  const grid = [
    [RED_CIRCLE, BLUE_CIRCLE],
    [BLUE_CIRCLE, RED_STAR],
  ];
  return [
    {
      agent_id: "player_a",
      grid,
      start: { row: 1, col: 1 },
      steps: [
        { sequence: 1, direction: "right", cell: { row: 1, col: 2 }, reasoning: "bounce" },
        { sequence: 2, direction: "left", cell: { row: 1, col: 1 }, reasoning: "bounce" },
        { sequence: 4, direction: "right", cell: { row: 1, col: 2 }, reasoning: "go blue" },
      ],
      end_sequence: 6,
      end_reasoning: "blue circle",
      final_cell: { row: 1, col: 2 },
      final_item: BLUE_CIRCLE,
      colour_order: ["red", "blue"],
      shape_order: ["star", "circle"],
      fill_order: [],
    },
    {
      agent_id: "player_b",
      grid,
      start: { row: 1, col: 1 },
      steps: [{ sequence: 3, direction: "down", cell: { row: 2, col: 1 }, reasoning: "down" }],
      end_sequence: 5,
      end_reasoning: null,
      final_cell: { row: 2, col: 1 },
      final_item: BLUE_CIRCLE,
      colour_order: ["blue", "red"],
      shape_order: ["circle", "star"],
      fill_order: [],
    },
  ];
}

describe("signal_game action log", () => {
  it("merges one call's steps and keeps both players in the round's numbering", () => {
    const log = actionLog(players());
    expect(log.map(group => [group.agentId, group.firstSequence, group.lastSequence])).toEqual([
      ["player_a", 1, 2],
      ["player_b", 3, 3],
      ["player_a", 4, 4],
      ["player_b", 5, 5],
      ["player_a", 6, 6],
    ]);
    expect(log[0]!.directions).toEqual(["right", "left"]);
    expect(log[log.length - 1]!.kind).toBe("end");
  });

  it("names an item as the players read it", () => {
    expect(itemLabel(RED_STAR)).toBe("red star");
    expect(itemLabel({ colour: "red", shape: null, fill: null })).toBe("red");
    expect(itemLabel({ colour: "red", shape: "circle", fill: "striped" })).toBe(
      "striped red circle"
    );
  });
});

describe("SignalGameRoundDetailPanel", () => {
  const extras: SignalGameRunExtras = {
    scenario_name: "signal_game",
    cases: [
      {
        round_number: 1,
        grid_size: 2,
        partner_colours_visible: false,
        shared_items: [BLUE_CIRCLE, RED_CIRCLE, RED_STAR],
        chance: 0.375,
        success: true,
        trigger: "both_finished",
        players: players(),
      },
    ],
  };

  it("draws both grids, the outcome and the reasoning", () => {
    const html = renderToStaticMarkup(
      createElement(SignalGameRoundDetailPanel, { roundNumber: 1, extras })
    );
    expect(html).toContain("Grid of player_a");
    expect(html).toContain("Grid of player_b");
    expect(html).toContain("point");
    expect(html).toContain("chance 38%");
    expect(html).toContain("blue circle");
    expect(html).toContain("bounce");
    expect(html).toContain("shapes listed: star, circle");
  });

  it("draws a striped item with a hatch pattern and a hollow one with an outline", () => {
    const filled: SignalGameRunExtras = {
      ...extras,
      cases: extras.cases.map(round => ({
        ...round,
        players: round.players.map(side => ({
          ...side,
          grid: [
            [
              { colour: "red", shape: "circle", fill: "striped" },
              { colour: "blue", shape: "star", fill: "hollow" },
            ],
            [
              { colour: "red", shape: "star", fill: "solid" },
              { colour: "red", shape: "star", fill: "solid" },
            ],
          ],
          fill_order: ["striped", "hollow", "solid"],
        })),
      })),
    };
    const html = renderToStaticMarkup(
      createElement(SignalGameRoundDetailPanel, { roundNumber: 1, extras: filled })
    );
    expect(html).toMatch(/fill="url\(#sg[A-Za-z0-9_-]*-stripe-red\)"/);
    expect(html).toContain("striped red circle");
    expect(html).toContain("fills listed: striped, hollow, solid");
  });

  it("renders nothing for another round or another scenario's extras", () => {
    expect(
      renderToStaticMarkup(createElement(SignalGameRoundDetailPanel, { roundNumber: 2, extras }))
    ).toBe("");
    expect(
      renderToStaticMarkup(
        createElement(SignalGameRoundDetailPanel, {
          roundNumber: 1,
          extras: { scenario_name: "move_a_box" },
        })
      )
    ).toBe("");
  });
});
