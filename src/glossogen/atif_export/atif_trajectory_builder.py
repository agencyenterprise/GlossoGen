"""Build ATIF trajectories for a run's agents from its JSONL event log.

Walks the events directly instead of going through ``build_message_history``, because
the reconstructed pydantic-ai history drops timestamps, token usage and which turns
came from scenario injections.

A seat produces one trajectory per generation. A new generation starts at an in-run
``AgentSwappedMidRun``, at the first registration of a derived run's replaced or
imported seat, and at a re-registration under a different model. A re-registration
under the same model is a resume and continues the current generation. A seeded
generation opens with the history its seat was seeded with, marked as copied.
"""

from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, NamedTuple

from pydantic_ai.messages import ModelMessage

from glossogen.atif_export.atif_models import (
    ATIF_SCHEMA_VERSION,
    AtifAgent,
    AtifFinalMetrics,
    AtifStep,
    AtifTrajectory,
)
from glossogen.atif_export.atif_run_context import AtifRunContext, load_atif_run_context
from glossogen.atif_export.atif_step_builder import (
    RunnerPromptKind,
    build_agent_step,
    build_compaction_step,
    build_runner_prompt_step,
    build_step_metrics,
    build_system_prompt_step,
    failed_cycle_records,
)
from glossogen.atif_export.copied_context import build_swap_seed
from glossogen.atif_export.seed_history_steps import build_seed_steps
from glossogen.atif_export.tool_definition_reconstruction import ToolDefinitionSource
from glossogen.models.event import (
    AgentRegistered,
    AgentRunCycleFailed,
    AgentSwappedMidRun,
    ContextCompacted,
    LLMResponseReceived,
    SimulationEvent,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.runners.communication_protocol import registered_runner_prompts
from glossogen.runtime.tool_definition_listing import select_tool_definitions
from glossogen.token_pricing import find_pricing


class _Generation(NamedTuple):
    """One stretch of a seat played under a single model, and the history it was seeded with.

    ``opening_event_id`` is the registration or swap that started it.
    """

    opening_event_id: str
    registration: AgentRegistered
    model: str
    provider: str
    seed: list[ModelMessage]
    events: list[SimulationEvent]


class _ToolDefinitions(NamedTuple):
    definitions: list[dict[str, Any]]
    source: ToolDefinitionSource


class _BuiltSteps(NamedTuple):
    """A generation's steps, and the cycles that failed after its last response."""

    steps: list[AtifStep]
    trailing_failed_cycles: list[AgentRunCycleFailed]


def build_agent_trajectories(
    context: AtifRunContext,
    agent_id: str,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Every generation of ``agent_id`` in the run, each as one ATIF trajectory.

    ``cutoff_round`` is exclusive, as in thread export: ``R`` keeps rounds
    ``1..R-1``; ``None`` keeps the whole run.
    """
    agent_events = _select_agent_events(
        events=context.events, agent_id=agent_id, cutoff_round=cutoff_round
    )
    generations = _split_generations(context=context, agent_events=agent_events, agent_id=agent_id)
    if not generations:
        raise ValueError(f"No agent {agent_id!r} registered in run {context.run_id}")
    return [
        _build_trajectory(
            context=context,
            generation=generation,
            generation_index=index,
            generation_count=len(generations),
            cutoff_round=cutoff_round,
        )
        for index, generation in enumerate(generations, start=1)
    ]


async def build_agent_trajectories_from_run_dir(
    run_dir: Path,
    scenario_name: str,
    agent_id: str,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Load the run at ``run_dir`` and build ``agent_id``'s trajectories."""
    context = await load_atif_run_context(run_dir=run_dir, scenario_name=scenario_name)
    return build_agent_trajectories(context=context, agent_id=agent_id, cutoff_round=cutoff_round)


def registered_agent_ids(events: list[SimulationEvent]) -> list[str]:
    """Agent ids in the order they first registered."""
    agent_ids: list[str] = []
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id not in agent_ids:
            agent_ids.append(event.agent_id)
    return agent_ids


def _select_agent_events(
    events: list[SimulationEvent],
    agent_id: str,
    cutoff_round: int | None,
) -> list[SimulationEvent]:
    selected: list[SimulationEvent] = []
    for event in events:
        if getattr(event, "agent_id", None) != agent_id:
            continue
        if cutoff_round is not None and event.round_number >= cutoff_round:
            continue
        selected.append(event)
    return selected


def _split_generations(
    context: AtifRunContext,
    agent_events: list[SimulationEvent],
    agent_id: str,
) -> list[_Generation]:
    generations: list[_Generation] = []
    for event in agent_events:
        if isinstance(event, AgentRegistered):
            generation = _generation_opened_by(
                context=context, registration=event, current=generations
            )
            if generation is None:
                generations[-1].events.append(event)
            else:
                generations.append(generation)
        elif isinstance(event, AgentSwappedMidRun):
            if not generations:
                raise ValueError(f"Agent {agent_id!r} swapped before it registered")
            registration = _swapped_registration(
                registration=generations[-1].registration, swap=event
            )
            generations.append(
                _Generation(
                    opening_event_id=event.event_id,
                    registration=registration,
                    model=event.new_model,
                    provider=event.new_provider,
                    seed=build_swap_seed(
                        events=context.events, swap=event, registration=registration
                    ),
                    events=[],
                )
            )
        elif generations:
            generations[-1].events.append(event)
    return generations


def _swapped_registration(
    registration: AgentRegistered,
    swap: AgentSwappedMidRun,
) -> AgentRegistered:
    """The seat's registration with the prompt the swap seeded its new agent with.

    A swap recorded before the prompt was logged keeps the registered one, which is
    what the swap used unless it set a prompt of its own.
    """
    if swap.system_prompt is None:
        return registration
    return registration.model_copy(update={"system_prompt": swap.system_prompt})


def _generation_opened_by(
    context: AtifRunContext,
    registration: AgentRegistered,
    current: list[_Generation],
) -> _Generation | None:
    """The generation a registration starts, or ``None`` when it resumes the current one."""
    copied = context.copied_context
    seed: list[ModelMessage] = []
    if current:
        enters_seeded_seat = (
            registration.agent_id == copied.seeded_agent_id
            and registration.event_id not in copied.copied_event_ids
            and current[-1].registration.event_id in copied.copied_event_ids
        )
        if enters_seeded_seat:
            seed = copied.boundary_seed
        elif current[-1].model == registration.model:
            return None
    return _Generation(
        opening_event_id=registration.event_id,
        registration=registration,
        model=registration.model,
        provider=registration.provider,
        seed=seed,
        events=[],
    )


def _build_steps(context: AtifRunContext, generation: _Generation) -> _BuiltSteps:
    """The generation's turns as the model received them.

    Injections and world events are not steps of their own: they reach the model
    as the result of its ``read_notifications`` calls, where they already appear.
    A cycle's responses are counted so the step that closes it, the one carrying
    the cycle's usage, says how many LLM calls its metrics cover.
    """
    copied_ids = context.copied_context.copied_event_ids
    pricing = find_pricing(
        model=generation.model,
        provider=generation.provider,
        at=generation.registration.timestamp,
    )
    results_by_call_id = {
        event.call_id: event for event in generation.events if isinstance(event, ToolResultReceived)
    }
    invoked_at = {
        event.call_id: event.timestamp
        for event in generation.events
        if isinstance(event, ToolCallInvoked)
    }
    steps = [
        build_system_prompt_step(
            step_id=1,
            registration=generation.registration,
            copied=generation.opening_event_id in copied_ids,
        )
    ]
    steps.extend(build_seed_steps(first_step_id=2, history=generation.seed))
    next_prompt: RunnerPromptKind | None = _first_prompt(generation=generation)
    failed_cycles: list[AgentRunCycleFailed] = []
    cycle_response_count = 0
    for event in sorted(
        generation.events, key=lambda item: _turn_time(event=item, invoked_at=invoked_at)
    ):
        copied = event.event_id in copied_ids
        if isinstance(event, AgentRegistered):
            # A relaunch under the same model resumes the agent with its history.
            next_prompt = RunnerPromptKind.CONTINUE
        elif isinstance(event, ContextCompacted):
            steps.append(build_compaction_step(step_id=len(steps) + 1, event=event, copied=copied))
        elif isinstance(event, AgentRunCycleFailed):
            failed_cycles.append(event)
            next_prompt = RunnerPromptKind.CONTINUE
        elif isinstance(event, LLMResponseReceived):
            if next_prompt is not None:
                steps.append(
                    build_runner_prompt_step(
                        step_id=len(steps) + 1,
                        prompt=_prompt_text(kind=next_prompt, registration=generation.registration),
                        kind=next_prompt,
                        copied=copied,
                    )
                )
            cycle_response_count += 1
            # Usage is logged on a cycle's last response, so the next response opens a new cycle.
            closes_cycle = build_step_metrics(usage=event.usage, pricing=pricing) is not None
            llm_call_count: int | None = None
            if closes_cycle:
                llm_call_count = cycle_response_count
            steps.append(
                build_agent_step(
                    step_id=len(steps) + 1,
                    event=event,
                    model_name=generation.model,
                    pricing=pricing,
                    results_by_call_id=results_by_call_id,
                    failed_cycles=failed_cycles,
                    copied=copied,
                    started_at=_turn_time(event=event, invoked_at=invoked_at),
                    llm_call_count=llm_call_count,
                )
            )
            failed_cycles = []
            next_prompt = None
            if closes_cycle:
                next_prompt = RunnerPromptKind.CONTINUE
                cycle_response_count = 0
    return _BuiltSteps(steps=steps, trailing_failed_cycles=failed_cycles)


def _first_prompt(generation: _Generation) -> RunnerPromptKind:
    """A fresh agent starts with the initial prompt; one seeded with history continues."""
    if generation.seed:
        return RunnerPromptKind.CONTINUE
    return RunnerPromptKind.INITIAL


def _prompt_text(kind: RunnerPromptKind, registration: AgentRegistered) -> str:
    """The runner prompt of that kind the registered agent ran with."""
    prompts = registered_runner_prompts(registration=registration)
    if kind is RunnerPromptKind.INITIAL:
        return prompts.initial
    return prompts.continuation


def _turn_time(event: SimulationEvent, invoked_at: dict[str, datetime]) -> datetime:
    """When an event reached or left the agent.

    A response's first tool invocation, otherwise the event's log time.
    """
    if isinstance(event, LLMResponseReceived):
        call_times = [
            invoked_at[call.call_id] for call in event.tool_calls if call.call_id in invoked_at
        ]
        if call_times:
            return min(call_times)
    return event.timestamp


def _resolve_tool_definitions(
    registration: AgentRegistered,
    reconstructed: list[RecordedToolDefinition] | None,
) -> _ToolDefinitions:
    if registration.tool_definitions:
        recorded = registration.tool_definitions
        source = ToolDefinitionSource.RECORDED
    elif reconstructed is not None:
        recorded = select_tool_definitions(
            definitions=reconstructed, tool_names=registration.tool_names
        )
        source = ToolDefinitionSource.RECONSTRUCTED
    else:
        return _ToolDefinitions(
            definitions=[{"name": name} for name in dict.fromkeys(registration.tool_names)],
            source=ToolDefinitionSource.NAMES_ONLY,
        )
    return _ToolDefinitions(
        definitions=[definition.model_dump(mode="json") for definition in recorded],
        source=source,
    )


def _build_final_metrics(steps: list[AtifStep]) -> AtifFinalMetrics:
    """Token and cost totals over the steps played in this run; ``total_steps`` counts every step.

    A copied step keeps the metrics its source run logged, but the source already
    accounts for that spend, so summing it here would count it twice across a source
    and its forks. With no measured step the totals are ``None``: nothing was
    measured, which is not the same as a measured zero.
    """
    step_metrics = [
        step.metrics for step in steps if step.metrics is not None and not step.is_copied_context
    ]
    if not step_metrics:
        return AtifFinalMetrics(
            total_prompt_tokens=None,
            total_completion_tokens=None,
            total_cached_tokens=None,
            total_cost_usd=None,
            total_steps=len(steps),
        )
    costs = [metrics.cost_usd for metrics in step_metrics]
    total_cost_usd: float | None = None
    if all(cost is not None for cost in costs):
        total_cost_usd = sum(cost for cost in costs if cost is not None)
    return AtifFinalMetrics(
        total_prompt_tokens=sum(metrics.prompt_tokens for metrics in step_metrics),
        total_completion_tokens=sum(metrics.completion_tokens for metrics in step_metrics),
        total_cached_tokens=sum(metrics.cached_tokens for metrics in step_metrics),
        total_cost_usd=total_cost_usd,
        total_steps=len(steps),
    )


def _build_trajectory(
    context: AtifRunContext,
    generation: _Generation,
    generation_index: int,
    generation_count: int,
    cutoff_round: int | None,
) -> AtifTrajectory:
    registration = generation.registration
    trajectory_id = f"{context.run_id}/{registration.agent_id}"
    if generation_count > 1:
        trajectory_id = f"{trajectory_id}/gen{generation_index}"
    built = _build_steps(context=context, generation=generation)
    extra: dict[str, Any] = {
        "scenario_name": context.scenario_name,
        "scenario_config": context.scenario_config,
        "generation": generation_index,
        "cutoff_round": cutoff_round,
    }
    if built.trailing_failed_cycles:
        # Failed cycles are recorded on the response that follows them; these had none.
        extra["failed_cycles_after_last_response"] = failed_cycle_records(
            failures=built.trailing_failed_cycles
        )
    tools = _resolve_tool_definitions(
        registration=registration,
        reconstructed=context.reconstructed_tool_definitions,
    )
    return AtifTrajectory(
        schema_version=ATIF_SCHEMA_VERSION,
        session_id=context.run_id,
        trajectory_id=trajectory_id,
        agent=AtifAgent(
            name=f"glossogen:{context.scenario_name}/{registration.role_name}",
            version=version("glossogen"),
            model_name=generation.model,
            tool_definitions=tools.definitions,
            extra={
                "agent_id": registration.agent_id,
                "provider": generation.provider,
                "channel_ids": registration.channel_ids,
                "max_tokens": registration.max_tokens,
                "tool_definitions_source": tools.source.value,
            },
        ),
        steps=built.steps,
        final_metrics=_build_final_metrics(steps=built.steps),
        extra=extra,
    )


def build_run_trajectories(
    context: AtifRunContext,
    cutoff_round: int | None,
) -> list[AtifTrajectory]:
    """Every agent's trajectories, agents in registration order."""
    return [
        trajectory
        for agent_id in registered_agent_ids(events=context.events)
        for trajectory in build_agent_trajectories(
            context=context,
            agent_id=agent_id,
            cutoff_round=cutoff_round,
        )
    ]


def trajectory_file_name(trajectory: AtifTrajectory) -> str:
    """``<agent_id>.json``, or ``<agent_id>.gen<k>.json`` for a seat with several generations."""
    session_prefix = f"{trajectory.session_id}/"
    local_id = trajectory.trajectory_id.removeprefix(session_prefix)
    return f"{local_id.replace('/', '.')}.json"


def serialize_trajectory(trajectory: AtifTrajectory) -> str:
    """The ATIF JSON document, with unset optional fields omitted as the spec expects."""
    return trajectory.model_dump_json(indent=2, exclude_none=True)
