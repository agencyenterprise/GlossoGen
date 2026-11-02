import type { components } from "@/types/api.gen";
import { humanize } from "./format";

type AgentModelSummary = components["schemas"]["AgentModelSummary"];
type RoundResultTally = components["schemas"]["RoundResultTally"];

/** One model a run's agents played, and how many agents played it. */
export interface ModelCount {
  model: string;
  count: number;
}

/** The models a run's agents played, in the order the agents registered, each
 *  with the number of agents that played it. */
export function countAgentModels(agentModels: AgentModelSummary[]): ModelCount[] {
  const counts = new Map<string, number>();
  for (const agent of agentModels) {
    counts.set(agent.model, (counts.get(agent.model) ?? 0) + 1);
  }
  return Array.from(counts, ([model, count]) => ({ model, count }));
}

/** The models as one short line: `model ×2 · other`. A model one agent played
 *  carries no count. */
export function formatModelCounts(counts: ModelCount[]): string {
  return counts
    .map(({ model, count }) => {
      if (count === 1) {
        return model;
      }
      return `${model} ×${count}`;
    })
    .join(" · ");
}

/** Which agent played which model, one agent per line, for a hover title. */
export function describeAgentModels(agentModels: AgentModelSummary[]): string {
  return agentModels.map(agent => `${agent.role_name}: ${agent.model}`).join("\n");
}

/** The rounds the scenario judged successful, as `2/3`, or per team as
 *  `Team A 2/3 · Team B 1/3`. Null when the scenario judged no rounds. */
export function formatRoundResults(tallies: RoundResultTally[]): string | null {
  if (tallies.length === 0) {
    return null;
  }
  return tallies
    .map(tally => {
      const fraction = `${tally.succeeded}/${tally.judged}`;
      if (tally.team_id === null) {
        return fraction;
      }
      return `${humanize(tally.team_id)} ${fraction}`;
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
