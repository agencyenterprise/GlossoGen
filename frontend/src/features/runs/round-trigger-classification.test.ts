import { describe, expect, it } from "vitest";
import { containerYardStackingPlugin } from "./container_yard_stacking/plugin";
import { DEFAULT_SCENARIO_PLUGIN } from "./default-plugin";
import { textcraftSharedWorkspacePlugin } from "./textcraft_shared_workspace/plugin";

describe("round trigger classification", () => {
  it("textcraft classifies every trigger its world ends a round with", () => {
    const classify = textcraftSharedWorkspacePlugin.classifyRoundTrigger;
    expect(classify("all_targets_satisfied")).toBe("success");
    expect(classify("budget_exhausted")).toBe("failure");
    expect(classify("actions_exhausted")).toBe("failure");
    expect(classify("team_tokens_exhausted")).toBe("failure");
    expect(classify("all_agents_waiting")).toBeNull();
  });

  it("container yard classifies its own two triggers and nothing else", () => {
    const classify = containerYardStackingPlugin.classifyRoundTrigger;
    expect(classify("round_completed")).toBe("success");
    expect(classify("round_failed")).toBe("failure");
    expect(classify("round_timeout")).toBeNull();
  });

  it("a scenario without a plug-in classifies nothing", () => {
    expect(DEFAULT_SCENARIO_PLUGIN.classifyRoundTrigger("round_completed")).toBeNull();
  });
});
