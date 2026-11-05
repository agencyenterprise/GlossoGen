import type { components } from "@/types/api.gen";
import { withThinking } from "./format";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];
type PlayedModel = components["schemas"]["PlayedModel"];
type RoundResultTally = components["schemas"]["RoundResultTally"];
type RunSummary = components["schemas"]["RunSummary"];

/** One model a run's agents played at one reasoning effort, and how many
 *  agents played it. */
export interface ModelCount {
  model: string;
  thinking: PlayedModel["thinking"];
  count: number;
}

/** The models a run's agents played, in the order the agents first played them,
 *  each with the number of agents that played it at any point. The same model
 *  at two reasoning efforts counts as two. An agent that played a model twice,
 *  around a swap away from it, counts once. */
export function countAgentModels(agentModels: AgentModelSummary[]): ModelCount[] {
  const counts = new Map<string, ModelCount>();
  for (const agent of agentModels) {
    const seen = new Set<string>();
    for (const played of agent.played) {
      const key = JSON.stringify([played.model, played.thinking]);
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      const count = counts.get(key);
      if (count === undefined) {
        counts.set(key, { model: played.model, thinking: played.thinking, count: 1 });
      } else {
        count.count += 1;
      }
    }
  }
  return Array.from(counts.values());
}

/** The models as one short line: `model (thinking high) ×2 · other`. A model
 *  sent no reasoning effort carries none, and one a single agent played
 *  carries no count. */
export function formatModelCounts(counts: ModelCount[]): string {
  return counts
    .map(({ model, thinking, count }) => {
      const name = withThinking(model, thinking);
      if (count === 1) {
        return name;
      }
      return `${name} ×${count}`;
    })
    .join(" · ");
}

/** The share of judged rounds that succeeded across every team, or null when
 *  none were judged. */
export function roundSuccessShare(tallies: RoundResultTally[]): number | null {
  const judged = tallies.reduce((sum, tally) => sum + tally.judged, 0);
  if (judged === 0) {
    return null;
  }
  const succeeded = tallies.reduce((sum, tally) => sum + tally.succeeded, 0);
  return succeeded / judged;
}

/** A point in a run's rounds where something changed who played: a fork, a
 *  replaced or imported agent, a model swap, an intern takeover, an observer
 *  swap. ``afterRound`` is the last round before the change. Every change at
 *  the same point shares one marker, described by its ``labels``. */
export interface RoundMarker {
  afterRound: number;
  labels: string[];
}

/** The points in a run's rounds where something changed who played, in round
 *  order. A change before round 1 has no marker, and neither has an intern
 *  takeover or observer swap the run has not reached. */
export function buildRoundMarkers(run: RunSummary): RoundMarker[] {
  const labelsByRound = new Map<number, string[]>();
  const mark = (afterRound: number, label: string) => {
    if (afterRound < 1) {
      return;
    }
    const labels = labelsByRound.get(afterRound) ?? [];
    labels.push(label);
    labelsByRound.set(afterRound, labels);
  };

  if (run.fork_at_round_source) {
    mark(
      run.fork_at_round_source.after_round,
      `Forked after round ${run.fork_at_round_source.after_round}`
    );
  }
  if (run.replace_agent_source) {
    const source = run.replace_agent_source;
    mark(
      source.after_round,
      `Replaced ${source.replaced_agent_id} after round ${source.after_round}`
    );
  }
  if (run.cross_run_replace_agent_source) {
    const source = run.cross_run_replace_agent_source;
    mark(
      source.after_round,
      `Imported ${source.replaced_agent_id} from ${source.source_b_run_id} after round ${source.after_round}`
    );
  }
  for (const agent of run.agent_models) {
    for (const played of agent.played.slice(1)) {
      mark(
        played.from_round - 1,
        `${agent.role_name} plays ${withThinking(`${played.provider}:${played.model}`, played.thinking)} from round ${played.from_round}`
      );
    }
  }
  // These two come from the run's config, not its log, so each is marked only
  // once the run has reached it. The intern plays from its takeover round on.
  // The swap fires at the start of the round after ``swap_round``, the last
  // round the original observers play.
  const config = run.scenario_config ?? {};
  const takeoverRound = config.intern_takeover_round;
  if (
    config.intern_enabled === true &&
    typeof takeoverRound === "number" &&
    run.current_round >= takeoverRound
  ) {
    mark(takeoverRound - 1, `Intern takes over at round ${takeoverRound}`);
  }
  const swapRound = config.swap_round;
  if (config.two_teams === true && typeof swapRound === "number" && run.current_round > swapRound) {
    mark(swapRound, `Observer swap after round ${swapRound}`);
  }

  return Array.from(labelsByRound, ([afterRound, labels]) => ({ afterRound, labels })).sort(
    (a, b) => a.afterRound - b.afterRound
  );
}
