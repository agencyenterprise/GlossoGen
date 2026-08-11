"""Apply in-run agent swaps on top of the configs rebuilt from registrations.

``extract_agent_configs`` reads ``AgentRegistered`` events, which the supervisor
writes once per agent at startup. An in-run swap does not write another one: it
records ``AgentSwappedMidRun`` and updates the runtime in place. So a run whose
agent was swapped rebuilds with the *predecessor's* model and system prompt,
and anything that re-runs an agent from its config afterwards runs the wrong
agent.

That matters for the probe metrics, which exist to ask an agent what it
remembers. Probing a swapped-in agent under its predecessor's model answers a
question nobody asked, and on a cross-model swap the answer comes from a
different provider entirely.
"""

from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import AgentSwappedMidRun, SimulationEvent


def apply_mid_run_swaps(
    agent_configs: list[AgentConfig],
    events: list[SimulationEvent],
) -> list[AgentConfig]:
    """Return the configs with each swapped agent moved onto its final model.

    The last swap for an agent wins, so a multi-swap run resolves to the
    generation that was running when the simulation ended. Agents that were
    never swapped are returned unchanged.

    The system prompt is left alone. A swap may carry its own
    (``SwapAgent.system_prompt``), but that is not recorded on the event, so
    inferring it here would be guesswork; the registration's prompt is the only
    one the log actually carries.
    """
    latest_model: dict[str, AgentSwappedMidRun] = {}
    for event in events:
        if isinstance(event, AgentSwappedMidRun):
            latest_model[event.agent_id] = event

    updated: list[AgentConfig] = []
    for config in agent_configs:
        swap = latest_model.get(config.agent_id)
        if swap is None:
            updated.append(config)
            continue
        updated.append(
            config.model_copy(update={"model": swap.new_model, "provider": swap.new_provider})
        )
    return updated
