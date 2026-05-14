"""The single MCP tool the veyru scenario exposes to its agents.

``stabilize_veyru`` is the field observer's stabilization action. Each
call submits free-text describing what the observer is doing; an LLM
judge compares it against the current stage's ground-truth expected
actions and decides whether it counts. Accepted calls advance the
team's stage index; the final accepted call marks the Veyru fully
stabilized. While the intern is silently observing (joined but not yet
taken over), every call's args + result are mirrored to the intern as
a one-way notification so they can learn the protocol.
"""

from typing import Callable

from schmidt.llm.provider import LLMProvider
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.scenario_protocol import ScenarioRuntimeHandle
from schmidt.scenarios.veyru.events import VeyruStabilizationJudged
from schmidt.scenarios.veyru.ids import INTERN_ID, NEW_SYMPTOMS_MARKER, STABILIZATION_SUCCESS_MARKER
from schmidt.scenarios.veyru.injection_rendering import is_intern_in_observer_state
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.stabilization_judge import judge_stabilization
from schmidt.scenarios.veyru.world import VeyruWorld


def build_mcp_tools(
    world: VeyruWorld,
    knobs: VeyruKnobs,
    judge_provider: LLMProvider,
    agent_display_names: dict[str, str],
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single-element ``stabilize_veyru`` tool list."""

    async def stabilize_veyru(ctx: ToolContext, action: str) -> str:
        """Apply a stabilization action to the caller's team Veyru."""
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            result_text = (
                "Cannot stabilize during the post-round discussion phase. "
                "Wait for the next round to begin."
            )
            await _maybe_notify_intern_stabilize(
                world=world,
                knobs=knobs,
                agent_display_names=agent_display_names,
                current_round=_current_round(get_runtime=get_runtime),
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text
        team_id = world.get_team_for_agent(agent_id=agent_id)
        team = world.teams[team_id]
        if agent_id != team.current_observer_id:
            raise ValueError("Only the field observer can stabilize Veyru entities")

        if not world.is_veyru_alive(team_id=team_id):
            result_text = "Cannot stabilize: Veyru has already collapsed."
            await _maybe_notify_intern_stabilize(
                world=world,
                knobs=knobs,
                agent_display_names=agent_display_names,
                current_round=_current_round(get_runtime=get_runtime),
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text
        if world.is_veyru_stabilized(team_id=team_id):
            result_text = "Veyru has already been stabilized."
            await _maybe_notify_intern_stabilize(
                world=world,
                knobs=knobs,
                agent_display_names=agent_display_names,
                current_round=_current_round(get_runtime=get_runtime),
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text

        current_stage = world.get_current_stage(team_id=team_id)
        if current_stage is None:
            result_text = "No Veyru to stabilize."
            await _maybe_notify_intern_stabilize(
                world=world,
                knobs=knobs,
                agent_display_names=agent_display_names,
                current_round=_current_round(get_runtime=get_runtime),
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text

        judgment = await judge_stabilization(
            provider=judge_provider,
            expected_actions=current_stage.judge_expected_actions,
            observer_action=action,
        )

        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=VeyruStabilizationJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    expected_actions=current_stage.judge_expected_actions,
                    judge_match=judgment.match,
                    judge_explanation=judgment.explanation,
                )
            )

        if judgment.match:
            has_more = await world.stabilize_veyru(team_id=team_id)
            if has_more:
                next_stage = world.get_current_stage(team_id=team_id)
                assert next_stage is not None
                result_text = (
                    f"{STABILIZATION_SUCCESS_MARKER}, but {NEW_SYMPTOMS_MARKER}. "
                    f"What you now observe: {next_stage.observable_symptoms} "
                    f"Report these to the engineer."
                )
                await _maybe_notify_intern_stabilize(
                    world=world,
                    knobs=knobs,
                    agent_display_names=agent_display_names,
                    current_round=_current_round(get_runtime=get_runtime),
                    caller_id=agent_id,
                    action=action,
                    result=result_text,
                )
                return result_text
            result_text = f"{STABILIZATION_SUCCESS_MARKER}."
            await _maybe_notify_intern_stabilize(
                world=world,
                knobs=knobs,
                agent_display_names=agent_display_names,
                current_round=_current_round(get_runtime=get_runtime),
                caller_id=agent_id,
                action=action,
                result=result_text,
            )
            return result_text

        result_text = "Stabilization ineffective. Ask the engineer for guidance."
        await _maybe_notify_intern_stabilize(
            world=world,
            knobs=knobs,
            agent_display_names=agent_display_names,
            current_round=_current_round(get_runtime=get_runtime),
            caller_id=agent_id,
            action=action,
            result=result_text,
        )
        return result_text

    return [
        ScenarioMcpTool(
            name="stabilize_veyru",
            description=(
                "Apply a stabilization action to the current Veyru. "
                "Describe exactly what you are doing to stabilize it."
            ),
            executor=stabilize_veyru,
        ),
    ]


def _current_round(get_runtime: Callable[[], ScenarioRuntimeHandle | None]) -> int | None:
    """Return the runtime's current round, or None when runtime is unbound."""
    runtime = get_runtime()
    if runtime is None:
        return None
    return runtime.current_round


async def _maybe_notify_intern_stabilize(
    world: VeyruWorld,
    knobs: VeyruKnobs,
    agent_display_names: dict[str, str],
    current_round: int | None,
    caller_id: str,
    action: str,
    result: str,
) -> None:
    """Notify the intern of a stabilize_veyru call + result while they observe.

    Fires only while the intern is in the observer state (after
    ``intern_join_round`` and before ``intern_takeover_round``). Delivered
    to the intern alone so the engineer never sees the tool-call trace.
    """
    if not is_intern_in_observer_state(world=world, knobs=knobs, current_round=current_round):
        return
    caller_display = agent_display_names.get(caller_id, caller_id)
    text = f'[stabilize_veyru] {caller_display} action="{action}"\nresult: {result}'
    await world.context.send_update_to_agent(
        agent_id=INTERN_ID,
        text=text,
    )
