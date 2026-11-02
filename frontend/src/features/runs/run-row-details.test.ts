import { expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { countAgentModels, formatModelCounts, roundSuccessShare } from "./run-row-details";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];

function agent(agentId: string, model: string): AgentModelSummary {
  return { agent_id: agentId, role_name: agentId, model, provider: "anthropic" };
}

it("counts the agents per model in registration order", () => {
  const counts = countAgentModels([
    agent("a", "claude-opus-4-7"),
    agent("b", "gpt-5.4"),
    agent("c", "claude-opus-4-7"),
  ]);

  expect(formatModelCounts(counts)).toBe("claude-opus-4-7 ×2 · gpt-5.4");
});

it("says nothing about models for a run that recorded no agents", () => {
  expect(countAgentModels([])).toEqual([]);
});

it("leaves the share out when the scenario judged no rounds rather than claiming zero", () => {
  expect(roundSuccessShare([])).toBeNull();
});

it("reports a share of zero when every judged round failed", () => {
  expect(roundSuccessShare([{ team_id: null, succeeded: 0, judged: 4, rounds: [] }])).toBe(0);
});
