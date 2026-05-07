/**
 * Agent-instance derivation: split each agent_id into one or more "generations"
 * based on AgentSwappedMidRun events.
 *
 * Generation 1 starts at round 1 with the registered AgentDetail. Each
 * AgentSwappedMidRun event for that agent_id begins a new generation that
 * inherits the role and channels from generation 1 but takes its model,
 * provider, and post-swap system prompt from the swap event. The generation's
 * round range runs from the swap round through one round before the next swap
 * (or until the run's last advanced round, or open-ended on a live run).
 */

import type { components } from "@/types/api.gen";

type AgentDetail = components["schemas"]["AgentDetail"];
type AgentSwapEventDTO = components["schemas"]["AgentSwapEventDTO"];

export type AgentInstance = {
  /** Synthetic key combining agent_id and 1-indexed generation, e.g. "field_observer:2". */
  instance_key: string;
  agent_id: string;
  /** 1-indexed generation; the original registered agent is generation 1. */
  generation: number;
  role_name: string;
  model: string;
  provider: string;
  system_prompt: string;
  channel_ids: string[];
  tool_names: string[];
  /** First round this instance was active (1 for generation 1, swap.round_number for swaps). */
  round_start: number;
  /** Last round this instance was active; null for the latest generation while the run is live. */
  round_end: number | null;
  /** True for the most recent generation per agent_id. */
  is_latest: boolean;
};

/**
 * Build the ordered instance list for a run.
 *
 * `max_round` is the highest round_number observed in the run's events; pass
 * null while the run is in_progress so the latest generation reports an
 * open-ended round_end. Swap events are sorted by (round_number, agent_id) for
 * deterministic ordering across SSE updates.
 */
export function deriveAgentInstances(
  agents: AgentDetail[],
  swap_events: AgentSwapEventDTO[],
  max_round: number | null,
  run_in_progress: boolean
): AgentInstance[] {
  const sorted_events = [...swap_events].sort((a, b) => {
    if (a.round_number !== b.round_number) {
      return a.round_number - b.round_number;
    }
    return a.agent_id.localeCompare(b.agent_id);
  });

  const events_by_agent = new Map<string, AgentSwapEventDTO[]>();
  for (const event of sorted_events) {
    const list = events_by_agent.get(event.agent_id) ?? [];
    list.push(event);
    events_by_agent.set(event.agent_id, list);
  }

  const instances: AgentInstance[] = [];
  for (const agent of agents) {
    const events_for_agent = events_by_agent.get(agent.agent_id) ?? [];
    const total_generations = events_for_agent.length + 1;

    // Generation 1 — the originally registered agent.
    const gen_1_end = events_for_agent[0]
      ? events_for_agent[0].round_number - 1
      : computeOpenEnd(max_round, run_in_progress);
    instances.push({
      instance_key: `${agent.agent_id}:1`,
      agent_id: agent.agent_id,
      generation: 1,
      role_name: agent.role_name,
      model: agent.model,
      provider: agent.provider,
      system_prompt: agent.system_prompt,
      channel_ids: agent.channel_ids,
      tool_names: agent.tool_names,
      round_start: 1,
      round_end: gen_1_end,
      is_latest: total_generations === 1,
    });

    // Generations 2+ — one per swap event.
    events_for_agent.forEach((event, index) => {
      const generation = index + 2;
      const next_event = events_for_agent[index + 1];
      const round_end = next_event
        ? next_event.round_number - 1
        : computeOpenEnd(max_round, run_in_progress);
      instances.push({
        instance_key: `${agent.agent_id}:${generation}`,
        agent_id: agent.agent_id,
        generation,
        role_name: agent.role_name,
        model: event.new_model,
        provider: event.new_provider,
        system_prompt: event.system_prompt,
        channel_ids: agent.channel_ids,
        tool_names: agent.tool_names,
        round_start: event.round_number,
        round_end,
        is_latest: generation === total_generations,
      });
    });
  }

  return instances;
}

function computeOpenEnd(max_round: number | null, run_in_progress: boolean): number | null {
  if (run_in_progress) {
    return null;
  }
  return max_round;
}

/**
 * Resolve a selectedAgent value into an AgentInstance. Accepts the suffixed
 * "agent_id:generation" form and the bare "agent_id" form (which resolves to
 * the latest generation for back-compat).
 */
export function resolveSelectedInstance(
  selected: string | null,
  instances: AgentInstance[]
): AgentInstance | null {
  if (selected === null) {
    return null;
  }
  const direct = instances.find(i => i.instance_key === selected);
  if (direct) {
    return direct;
  }
  // Bare agent_id → latest generation.
  const latest = instances.filter(i => i.agent_id === selected && i.is_latest).at(0);
  return latest ?? null;
}

/**
 * Group an agent_id's instances together for sidebar rendering. Ordering
 * matches the input `agents` list so the sidebar position is stable.
 */
export function groupInstancesByAgent(
  agents: AgentDetail[],
  instances: AgentInstance[]
): { agent_id: string; role_name: string; instances: AgentInstance[] }[] {
  return agents.map(agent => ({
    agent_id: agent.agent_id,
    role_name: agent.role_name,
    instances: instances.filter(i => i.agent_id === agent.agent_id),
  }));
}
