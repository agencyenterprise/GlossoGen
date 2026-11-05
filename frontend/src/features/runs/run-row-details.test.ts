import { expect, it } from "vitest";
import type { components } from "@/types/api.gen";
import {
  buildRoundMarkers,
  countAgentModels,
  formatModelCounts,
  roundSuccessShare,
} from "./run-row-details";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];
type RunSummary = components["schemas"]["RunSummary"];

function agent(agentId: string, ...models: string[]): AgentModelSummary {
  return {
    agent_id: agentId,
    role_name: agentId,
    model: models[0] ?? "",
    provider: "anthropic",
    played: models.map((model, index) => ({
      model,
      provider: "anthropic",
      thinking: null,
      from_round: 1 + index * 5,
    })),
  };
}

type Thinking = AgentModelSummary["played"][number]["thinking"];

function agentAtEfforts(agentId: string, model: string, ...efforts: Thinking[]): AgentModelSummary {
  return {
    agent_id: agentId,
    role_name: agentId,
    model,
    provider: "openai",
    played: efforts.map((thinking, index) => ({
      model,
      provider: "openai",
      thinking,
      from_round: 1 + index * 5,
    })),
  };
}

it("counts the agents per model in registration order", () => {
  const counts = countAgentModels([
    agent("a", "claude-opus-4-7"),
    agent("b", "gpt-5.4"),
    agent("c", "claude-opus-4-7"),
  ]);

  expect(formatModelCounts(counts)).toBe("claude-opus-4-7 ×2 · gpt-5.4");
});

it("counts a model swapped in mid-run alongside the one it replaced", () => {
  const counts = countAgentModels([
    agent("left", "claude-opus-5-5", "gpt-5.6-luna"),
    agent("right", "claude-opus-5-5"),
  ]);

  expect(formatModelCounts(counts)).toBe("claude-opus-5-5 ×2 · gpt-5.6-luna");
});

it("counts an agent once for a model it went back to", () => {
  const counts = countAgentModels([
    agent("left", "claude-opus-5-5", "gpt-5.6-luna", "claude-opus-5-5"),
  ]);

  expect(formatModelCounts(counts)).toBe("claude-opus-5-5 · gpt-5.6-luna");
});

it("names the reasoning effort each model was sent and counts each effort apart", () => {
  const counts = countAgentModels([
    agentAtEfforts("a", "gpt-6.1-sol", "high"),
    agentAtEfforts("b", "gpt-6.1-sol", "high"),
    agentAtEfforts("c", "gpt-6.1-sol", "low"),
    agentAtEfforts("d", "gpt-6.1-sol", null),
  ]);

  expect(formatModelCounts(counts)).toBe(
    "gpt-6.1-sol (thinking high) ×2 · gpt-6.1-sol (thinking low) · gpt-6.1-sol"
  );
});

it("counts a swap that changed only the reasoning effort as a second entry", () => {
  const counts = countAgentModels([agentAtEfforts("left", "gpt-6.1-sol", "low", "high")]);

  expect(formatModelCounts(counts)).toBe(
    "gpt-6.1-sol (thinking low) · gpt-6.1-sol (thinking high)"
  );
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

function runSummary(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_id: "veyru/1",
    scenario_name: "veyru",
    scenario_description: "",
    scenario_config: {},
    status: "scenario_complete",
    timestamp: "2026-10-30T10:00:00Z",
    total_messages: 0,
    total_cost_usd: 0,
    duration_seconds: 0,
    has_evaluation: false,
    evaluation_scores: null,
    evaluation_in_progress: false,
    run_dir: "runs/veyru/1",
    fork_source: null,
    replace_agent_source: null,
    cross_run_replace_agent_source: null,
    fork_at_round_source: null,
    models: [],
    provider: "anthropic",
    agent_models: [],
    labels: [],
    has_note: false,
    current_round: 0,
    round_results: [],
    evaluation_content_hash: null,
    ...overrides,
  };
}

it("marks nothing on a run nothing changed partway through", () => {
  expect(buildRoundMarkers(runSummary({ agent_models: [agent("a", "claude-opus-5-5")] }))).toEqual(
    []
  );
});

it("marks a mid-run swap after the round before the new model played", () => {
  const markers = buildRoundMarkers(
    runSummary({ agent_models: [agent("left", "claude-opus-5-5", "gpt-5.6-luna")] })
  );

  expect(markers).toEqual([
    { afterRound: 5, labels: ["left plays anthropic:gpt-5.6-luna from round 6"] },
  ]);
});

it("names the reasoning effort a mid-run swap changed to", () => {
  const markers = buildRoundMarkers(
    runSummary({ agent_models: [agentAtEfforts("left", "gpt-6.1-sol", "low", "high")] })
  );

  expect(markers).toEqual([
    { afterRound: 5, labels: ["left plays openai:gpt-6.1-sol (thinking high) from round 6"] },
  ]);
});

it("puts a replacement and the model change it caused on one marker", () => {
  const markers = buildRoundMarkers(
    runSummary({
      replace_agent_source: {
        source_run_id: "veyru/0",
        replaced_agent_id: "left",
        after_round: 5,
        target_event_id: "event-1",
        replacement_model: "gpt-5.6-luna",
        replacement_provider: "anthropic",
        replaced_at: "2026-10-30T10:00:00Z",
      },
      agent_models: [agent("left", "claude-opus-5-5", "gpt-5.6-luna")],
    })
  );

  expect(markers).toEqual([
    {
      afterRound: 5,
      labels: ["Replaced left after round 5", "left plays anthropic:gpt-5.6-luna from round 6"],
    },
  ]);
});

it("marks an intern takeover before its round and an observer swap after swap_round", () => {
  // swap_round is the last round the original observers play; the swap fires
  // at the start of the round after it.
  const markers = buildRoundMarkers(
    runSummary({
      current_round: 10,
      scenario_config: {
        intern_enabled: true,
        intern_takeover_round: 4,
        two_teams: true,
        swap_round: 8,
      },
    })
  );

  expect(markers).toEqual([
    { afterRound: 3, labels: ["Intern takes over at round 4"] },
    { afterRound: 8, labels: ["Observer swap after round 8"] },
  ]);
});

it("leaves out an observer swap the run has not reached", () => {
  const config = { two_teams: true, swap_round: 8 };

  expect(buildRoundMarkers(runSummary({ current_round: 5, scenario_config: config }))).toEqual([]);
  expect(buildRoundMarkers(runSummary({ current_round: 8, scenario_config: config }))).toEqual([]);
  expect(
    buildRoundMarkers(runSummary({ current_round: 9, scenario_config: config })).map(
      marker => marker.afterRound
    )
  ).toEqual([8]);
});

it("leaves out an intern takeover the run has not reached", () => {
  const config = { intern_enabled: true, intern_takeover_round: 4 };

  expect(buildRoundMarkers(runSummary({ current_round: 3, scenario_config: config }))).toEqual([]);
  expect(
    buildRoundMarkers(runSummary({ current_round: 4, scenario_config: config })).map(
      marker => marker.afterRound
    )
  ).toEqual([3]);
});
