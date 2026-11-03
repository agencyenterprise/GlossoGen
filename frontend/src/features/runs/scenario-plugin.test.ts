import { describe, expect, it } from "vitest";
import { isScenarioExtras } from "./scenario-plugin";

describe("isScenarioExtras", () => {
  it("accepts the variant tagged with the scenario's name", () => {
    expect(isScenarioExtras({ scenario_name: "signal_game", cases: [] }, "signal_game")).toBe(true);
  });

  it("rejects another scenario's extras", () => {
    expect(isScenarioExtras({ scenario_name: "move_a_box", cases: [] }, "signal_game")).toBe(false);
  });

  it("rejects a run with no extras and anything that is not an object", () => {
    expect(isScenarioExtras(null, "veyru")).toBe(false);
    expect(isScenarioExtras(undefined, "veyru")).toBe(false);
    expect(isScenarioExtras("veyru", "veyru")).toBe(false);
  });

  it("rejects, at compile time, a name no variant carries", () => {
    // tsc fails this file if the constraint on the name goes away.
    // @ts-expect-error: no scenario_extras variant is tagged "no_such_scenario".
    isScenarioExtras({ scenario_name: "no_such_scenario" }, "no_such_scenario");
  });
});
