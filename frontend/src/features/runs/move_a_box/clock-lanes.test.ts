import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { ClockLanes } from "./clock-lanes";
import { clockTicks, finishText, laneShares, momentAt, waitUntilText } from "./clock-lanes-labels";

type MoveABoxRoundClock = components["schemas"]["MoveABoxRoundClock"];
type MoveABoxWaitSpan = components["schemas"]["MoveABoxWaitSpan"];

function wait(overrides: Partial<MoveABoxWaitSpan>): MoveABoxWaitSpan {
  return {
    start_s: 4,
    end_s: 9,
    timeout_s: null,
    cause: "other_acted",
    woken_by: "operator_a",
    ...overrides,
  };
}

/** operator_a thinks, carries one action and finishes; operator_b waits until it lands. */
const CLOCK: MoveABoxRoundClock = {
  duration_s: 12,
  step_duration_s: 5,
  lanes: [
    {
      agent_id: "operator_a",
      thinking: [{ start_s: 0, end_s: 4, cost_s: 4, output_tokens: 150 }],
      actions: [
        {
          start_s: 4,
          end_s: 9,
          sequence: 1,
          action: "cart",
          direction: "left",
          reasoning: "Toward the shared bay.",
        },
      ],
      finishes: [{ at_s: 9, crate_marking: "CR-1", bay: 5, reasoning: "Done here." }],
      waits: [wait({ start_s: 9, end_s: 12, cause: "run_ended", woken_by: null })],
    },
    {
      agent_id: "operator_b",
      thinking: [
        { start_s: 0, end_s: 4, cost_s: 4, output_tokens: 150 },
        { start_s: 9, end_s: 12, cost_s: 3, output_tokens: 100 },
      ],
      actions: [],
      finishes: [],
      waits: [wait({})],
    },
  ],
};

describe("what an operator was doing at one second", () => {
  it("says what ends each wait, from inside it", () => {
    expect(waitUntilText(wait({}))).toBe("until operator_a's action lands at 9.0 s");
    expect(waitUntilText(wait({ cause: "timer", timeout_s: 15, woken_by: null }))).toBe(
      "until its 15.0 s timer runs out at 9.0 s"
    );
    expect(waitUntilText(wait({ cause: "next_round", woken_by: null }))).toBe(
      "until the next round"
    );
  });

  it("reads each lane at the crosshair's second", () => {
    const [laneA, laneB] = CLOCK.lanes;
    expect(momentAt(laneA!, 2)).toEqual({
      activity: "thinking",
      headline: "Thinking: 150 tokens cost 4.0 s",
      detail: null,
    });
    expect(momentAt(laneA!, 6)).toEqual({
      activity: "acting",
      headline: "cart ←, lands at 9.0 s",
      detail: "Toward the shared bay.",
    });
    expect(momentAt(laneB!, 6).headline).toBe("Waiting until operator_a's action lands at 9.0 s");
    expect(momentAt(laneB!, 9).activity).toBe("thinking");
  });

  it("names a finish left on none of its operator's bays, and an unknown waker", () => {
    const lane = {
      ...CLOCK.lanes[0]!,
      finishes: [{ at_s: 9, crate_marking: "CR-1", bay: null, reasoning: null }],
      waits: [],
    };
    expect(momentAt(lane, 10).headline).toBe("Finished on no assigned bay");
    expect(finishText(lane)).toBe("Finished on no assigned bay at 9.0 s");
    expect(waitUntilText(wait({ woken_by: null }))).toBe(
      "until another operator's action lands at 9.0 s"
    );
  });

  it("splits an operator's round into shares", () => {
    expect(laneShares(CLOCK.lanes[1]!, 12)).toEqual({
      thinking: 7 / 12,
      acting: 0,
      waiting: 5 / 12,
    });
  });

  it("counts the axis in steps far enough apart", () => {
    expect(clockTicks(12, 40, 56)).toEqual([0, 2, 4, 6, 8, 10, 12]);
    const long = clockTicks(300, 6, 56);
    expect(long.slice(0, 3)).toEqual([0, 10, 20]);
    expect(long[long.length - 1]).toBe(300);
  });
});

describe("the clock lanes", () => {
  it("draws a ribbon per operator, the finish pin and the arrow a landing caused", () => {
    const html = renderToStaticMarkup(createElement(ClockLanes, { clock: CLOCK }));

    expect(html).toContain("operator_a on the clock");
    expect(html).toContain("operator_b on the clock");
    expect(html).toContain("the round ran 12 s");
    expect(html).toContain("each action takes 5 s");
    expect(html).toContain("bay 5");
    expect(html).toContain("think 58% · act 0% · wait 42%");
    expect(html).toContain("←");
    // One wake arrow, in operator_a's colour: its landing ended operator_b's wait.
    expect(html.match(/<path d="[^"]+" fill="#3b82f6"/g)).toHaveLength(1);
  });

  it("starts with no second chosen and says how to choose one", () => {
    const html = renderToStaticMarkup(createElement(ClockLanes, { clock: CLOCK }));

    expect(html).toContain("Point at the lanes");
    expect(html).toContain('aria-valuetext="No second chosen"');
    expect(html).toContain("Finished on bay 5 at 9.0 s");
    expect(html).toContain("Did not finish");
  });
});
