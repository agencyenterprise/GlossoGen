import { expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import { resolveRunDetailLine } from "./run-row";

type RunSummary = components["schemas"]["RunSummary"];
type AgentModelSummary = components["schemas"]["AgentModelSummary"];

function agents(count: number): AgentModelSummary[] {
  return Array.from({ length: count }, (_, index) => ({
    agent_id: `operator_${index}`,
    role_name: `operator_${index}`,
    model: "gpt-6.1-sol",
    provider: "openai",
  }));
}

function runSummary(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_id: "move_a_box/1",
    scenario_name: "move_a_box",
    scenario_description: "",
    status: "completed",
    timestamp: "2026-10-30T10:00:00Z",
    total_messages: 0,
    total_cost_usd: 0,
    duration_seconds: 0,
    has_evaluation: false,
    evaluation_scores: null,
    evaluation_in_progress: false,
    run_dir: "runs/move_a_box/1",
    models: ["gpt-6.1-sol"],
    provider: "openai",
    agent_models: [],
    labels: [],
    has_note: false,
    current_round: 0,
    ...overrides,
  } as RunSummary;
}

it("counts every agent that played, not the distinct models", () => {
  const line = resolveRunDetailLine(
    runSummary({ agent_models: agents(4), duration_seconds: 90, total_cost_usd: 2.75 })
  );

  expect(line).toBe("4 agents / 1m 30s / $2.75");
});

it("says agent, not agents, for a scenario played alone", () => {
  const line = resolveRunDetailLine(runSummary({ agent_models: agents(1) }));

  expect(line).toBe("1 agent");
});

it("leaves the count out when the run recorded no agents rather than claiming zero", () => {
  const line = resolveRunDetailLine(runSummary({ agent_models: [], duration_seconds: 90 }));

  expect(line).toBe("1m 30s");
});

it("is null when the run recorded nothing at all", () => {
  expect(resolveRunDetailLine(runSummary({}))).toBeNull();
});
