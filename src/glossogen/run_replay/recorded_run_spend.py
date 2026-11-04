"""What a run had spent before a resumed process takes it over, read from its log.

Each process that writes a run's log ends with a ``SimulationEnded`` whose
``total_cost_usd`` covers every process before it, so the last one is the run's
spend up to that point. Spend logged after it, by a process that was killed
before it could log an end, survives only as the usage on its
``LLMResponseReceived`` and closing-prompt events, priced here at each event's
time. A ``SimulationEnded`` of ``0.0`` was written by a build that did not
record a failed process's spend, so the usage before it stands in for it.

Builds before 2026-11-04 wrote each process's own spend rather than the run's.
A log already resumed under one of them holds several such ends, and only the
last is read, so the earlier processes' spend is missed.

Events cloned from a derived run's source are not the derived run's spend.
``own_events_from`` is when the derived run began, and events before it are
skipped.
"""

from datetime import datetime

from glossogen.models.event import (
    AgentRegistered,
    AgentSwappedMidRun,
    ClosingPromptAnswered,
    ClosingPromptFailed,
    LLMResponseReceived,
    SimulationEnded,
    SimulationEvent,
)
from glossogen.token_pricing import BilledModel, usage_cost_usd


def recorded_run_spend_usd(
    events: list[SimulationEvent], own_events_from: datetime | None
) -> float:
    """The run's spend recorded in ``events``, in USD.

    ``own_events_from`` is ``None`` for a run that is not derived, which owns
    every event in its log.
    """
    billed_by_agent: dict[str, BilledModel] = {}
    usage_before_last_end = 0.0
    usage_since_last_end = 0.0
    spend_at_last_end = 0.0
    for event in events:
        # Registrations are read from cloned events too: a derived run's agents
        # keep the models the source registered them under.
        if isinstance(event, AgentRegistered):
            billed_by_agent[event.agent_id] = BilledModel(
                model=event.model, provider=event.provider
            )
            continue
        if isinstance(event, AgentSwappedMidRun):
            billed_by_agent[event.agent_id] = BilledModel(
                model=event.new_model, provider=event.new_provider
            )
            continue
        if own_events_from is not None and event.timestamp < own_events_from:
            continue
        if isinstance(event, SimulationEnded):
            usage_before_last_end += usage_since_last_end
            usage_since_last_end = 0.0
            if event.total_cost_usd > 0:
                spend_at_last_end = event.total_cost_usd
            else:
                spend_at_last_end = usage_before_last_end
        elif isinstance(event, (LLMResponseReceived, ClosingPromptAnswered, ClosingPromptFailed)):
            billed = billed_by_agent.get(event.agent_id)
            if billed is None:
                continue
            cost = usage_cost_usd(
                model=billed.model, provider=billed.provider, at=event.timestamp, usage=event.usage
            )
            if cost is not None:
                usage_since_last_end += cost
    return spend_at_last_end + usage_since_last_end
