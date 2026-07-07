"""The single MCP tool the orbital_anomaly scenario exposes to its agents.

``actuate_panel`` is the astronaut's corrective action. Each call submits
free text describing what the astronaut is doing at the panel; an LLM judge
compares it against the current stage's expected procedure and decides
whether it counts. Accepted calls advance the anomaly's stage index; the
final accepted call marks the vehicle fully stabilized.
"""

from collections.abc import Callable

from glossogen.llm.provider import LLMProvider
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.orbital_anomaly.actuation_judge import judge_actuation
from glossogen.scenarios.orbital_anomaly.events import OrbitalAnomalyActuationJudged
from glossogen.scenarios.orbital_anomaly.ids import (
    ACTUATION_SUCCESS_MARKER,
    ASTRONAUT_ID,
    NEW_ANOMALY_MARKER,
)
from glossogen.scenarios.orbital_anomaly.world import OrbitalAnomalyWorld


def build_mcp_tools(
    world: OrbitalAnomalyWorld,
    judge_provider: LLMProvider,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single-element ``actuate_panel`` tool list."""

    async def actuate_panel(ctx: ToolContext, action: str) -> str:
        """Carry out a corrective action at the panel."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != ASTRONAUT_ID:
            raise ValueError("Only the astronaut can operate the panel")
        if world.in_postmortem:
            return "Cannot operate the panel during the debrief phase. Wait for the next anomaly."
        if not world.is_vehicle_alive():
            return "Cannot act: the system has already been lost."
        if world.is_vehicle_stabilized():
            return "The vehicle is already stabilized."
        current_stage = world.get_current_stage()
        if current_stage is None:
            return "There is no active anomaly to act on."

        judgment = await judge_actuation(
            provider=judge_provider,
            expected_procedure=current_stage.judge_expected_actions,
            astronaut_action=action,
        )

        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=OrbitalAnomalyActuationJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    expected_actions=current_stage.judge_expected_actions,
                    judge_match=judgment.match,
                    judge_explanation=judgment.explanation,
                )
            )

        if not judgment.match:
            return (
                "Action ineffective. It does not match the corrective procedure for the current "
                "configuration. Ask the Systems Engineer for the procedure."
            )

        next_stage = await world.advance_stage()
        if next_stage is None:
            return f"{ACTUATION_SUCCESS_MARKER}. The vehicle is stabilized."
        return (
            f"{ACTUATION_SUCCESS_MARKER}, but {NEW_ANOMALY_MARKER}. "
            f"What you now see at the panel: {next_stage.cockpit_alarm} "
            f"{next_stage.panel_observation}"
        )

    return [
        ScenarioMcpTool(
            name="actuate_panel",
            description=(
                "Carry out a corrective action at the panel. "
                "Describe exactly what you are doing."
            ),
            executor=actuate_panel,
        ),
    ]
