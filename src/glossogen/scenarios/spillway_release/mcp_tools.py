"""The four MCP tools the spillway scenario exposes to its agents.

``read_gauge`` and ``open_gates`` belong to the dam operator, ``notify_park``
to the park ranger, and ``evacuate`` to civil defense. ``open_gates``,
``notify_park``, and ``evacuate`` record the agent's decision on the world
(the operator's gate setting is last-call-wins; the ranger and civil defense
commits are monotonic) and log a JSONL event. None of the tool results
reveals another agent's private information — in particular ``open_gates``
never echoes the resulting reservoir level, which would leak the inflow only
civil defense knows.
"""

from typing import Callable, Literal

from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.spillway_release.events import (
    SpillwayEvacuated,
    SpillwayGatesOpened,
    SpillwayParkNotified,
)
from glossogen.scenarios.spillway_release.ids import (
    CIVIL_DEFENSE_ID,
    DAM_OPERATOR_ID,
    PARK_RANGER_ID,
)
from glossogen.scenarios.spillway_release.spillway_cases import format_hours
from glossogen.scenarios.spillway_release.world import SpillwayWorld


def build_mcp_tools(
    world: SpillwayWorld,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the read_gauge / open_gates / notify_park / evacuate tool list."""

    async def read_gauge(ctx: ToolContext) -> str:
        """Report the current reservoir level and the collapse / supply thresholds."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != DAM_OPERATOR_ID:
            return "Only the dam operator can read the reservoir gauge."
        case = world.current_case
        if case is None:
            return "No active reservoir reading."
        return (
            f"Reservoir gauge: {case.start_level}% of capacity. "
            f"The dam collapses above {case.max_level}%; supply fails below {case.min_level}%."
        )

    async def open_gates(ctx: ToolContext, count: int, duration_hours: float) -> str:
        """Set the spillway gates for this round (last call wins).

        ``count`` is how many of the identical gates to open (0 holds them
        closed); ``duration_hours`` is how long to keep them open from the
        current time. Total water shed = count x per-gate rate x duration.
        """
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return "Cannot operate the gates during the discussion phase. Wait for the next round."
        if agent_id != DAM_OPERATOR_ID:
            return "Only the dam operator can open the gates."
        case = world.current_case
        if case is None:
            return "No active reservoir state."
        if count < 0 or count > case.gate_count:
            return f"count must be in [0, {case.gate_count}] (got {count})."
        if duration_hours < 0:
            return f"duration_hours must be >= 0 (got {duration_hours})."
        world.commit_gates(gate_count_opened=count, duration_hours=duration_hours)
        if count == 0 or duration_hours == 0:
            release_total = 0.0
            window_end = case.current_time_hours
            detail = "Gates held closed — no release this round."
        else:
            release_total = float(count * case.release_per_gate_per_hour * duration_hours)
            window_end = case.current_time_hours + duration_hours
            detail = (
                f"Gates set: {count} gate(s) for {duration_hours}h "
                f"(release window {format_hours(value=case.current_time_hours)}"
                f"-{format_hours(value=window_end)}). "
                f"Total water shed this round: {release_total:.0f}% of capacity."
            )
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=SpillwayGatesOpened(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    gate_count_opened=count,
                    duration_hours=duration_hours,
                    release_total=release_total,
                    window_start_hours=case.current_time_hours,
                    window_end_hours=window_end,
                )
            )
        return f"Acknowledged. {detail}"

    async def notify_park(ctx: ToolContext, action: Literal["close", "keep_closed"]) -> str:
        """Tell the park to close now or stay closed, securing the downstream area.

        Only works when the park is closeable; on a committed-event day the
        request is rejected and an evacuation is the only way to clear the area.
        """
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return "Cannot notify the park during the discussion phase. Wait for the next round."
        if agent_id != PARK_RANGER_ID:
            return "Only the park ranger can notify the park."
        case = world.current_case
        if case is None:
            return "No active park schedule."
        runtime = get_runtime()
        if not case.park_lockable:
            if runtime is not None:
                await runtime.event_logger.log(
                    event=SpillwayParkNotified(
                        agent_id=agent_id,
                        round_number=runtime.current_round,
                        action=action,
                        accepted=False,
                    )
                )
            return (
                "The park has a committed event today and cannot be closed. "
                "An evacuation is the only way to clear the downstream area for a release."
            )
        world.secure_park()
        if runtime is not None:
            await runtime.event_logger.log(
                event=SpillwayParkNotified(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    action=action,
                    accepted=True,
                )
            )
        return (
            f"Park secured ({action}). The downstream trails stay closed; "
            "the area is unoccupied, so a release this round will not endanger visitors."
        )

    async def evacuate(ctx: ToolContext) -> str:
        """Order a downstream evacuation, clearing the area of people for this round."""
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return (
                "Cannot order an evacuation during the discussion phase. Wait for the next round."
            )
        if agent_id != CIVIL_DEFENSE_ID:
            return "Only civil defense can order an evacuation."
        case = world.current_case
        if case is None:
            return "No active downstream area state."
        world.order_evacuation()
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=SpillwayEvacuated(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                )
            )
        return (
            "Evacuation ordered. The downstream area is cleared of people; "
            "a release this round will not harm anyone."
        )

    return [
        ScenarioMcpTool(
            name="read_gauge",
            description=(
                "Dam operator only. Report the current reservoir level (percent of "
                "capacity) and the collapse / supply thresholds. Takes no arguments."
            ),
            executor=read_gauge,
        ),
        ScenarioMcpTool(
            name="open_gates",
            description=(
                "Dam operator only. Set the spillway gates for this round. Args: "
                "count (how many identical gates to open, 0 holds them closed) and "
                "duration_hours (how long to keep them open from the current time). "
                "Total water shed = count x per-gate rate x duration_hours. You may "
                "call this again to revise the plan; the last call before the round "
                "ends is what counts."
            ),
            executor=open_gates,
        ),
        ScenarioMcpTool(
            name="notify_park",
            description=(
                "Park ranger only. Secure the downstream park so a release is safe. "
                "Args: action ('close' an open park, or 'keep_closed' one scheduled "
                "to open later). Rejected on a committed-event day (the park cannot "
                "be closed); coordinate an evacuation instead."
            ),
            executor=notify_park,
        ),
        ScenarioMcpTool(
            name="evacuate",
            description=(
                "Civil defense only. Order a downstream evacuation, clearing the area "
                "of people so a release this round harms no one. Takes no arguments."
            ),
            executor=evacuate,
        ),
    ]
