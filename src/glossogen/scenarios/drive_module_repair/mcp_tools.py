"""The single MCP tool the drive_module_repair scenario exposes.

``service_component`` is the field technician's action. Each call submits
free text describing the full service procedure being performed; an LLM judge compares
it against the current stage's ground-truth expected action (component +
tool + torque + calibration) and decides whether it counts. Accepted calls
advance the stage index in order (only the current required replacement is
accepted, which hard-enforces the diagnostics engineer's ordering); the
final accepted call marks the device fully repaired.
"""

from typing import Callable

from glossogen.llm.provider import LLMProvider
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.scenario_protocol import ScenarioRuntimeHandle
from glossogen.scenarios.drive_module_repair.events import DriveModuleReplacementJudged
from glossogen.scenarios.drive_module_repair.ids import (
    FIELD_TECHNICIAN_ID,
    REPLACEMENT_ACCEPTED_MARKER,
    REPLACEMENT_INEFFECTIVE_MARKER,
    SERVICE_COMPONENT_TOOL,
)
from glossogen.scenarios.drive_module_repair.replacement_judge import judge_replacement
from glossogen.scenarios.drive_module_repair.world import DriveModuleWorld


def build_mcp_tools(
    world: DriveModuleWorld,
    judge_provider: LLMProvider,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the single-element ``service_component`` tool list."""

    async def service_component(ctx: ToolContext, action: str) -> str:
        """Perform a component's full service procedure on the drive module."""
        agent_id = resolve_agent_id(ctx=ctx)
        if agent_id != FIELD_TECHNICIAN_ID:
            return "Only the field technician can replace components."
        if world.in_postmortem:
            return (
                "Cannot service the module during the post-round discussion phase. "
                "Wait for the next round to begin."
            )
        if world.round_budget_exceeded:
            return f"{REPLACEMENT_INEFFECTIVE_MARKER}. The service window has already closed."
        if world.is_device_repaired():
            return "The device has already been fully repaired this round."
        current_stage = world.get_current_stage()
        if current_stage is None:
            return "No component to replace."

        judgment = await judge_replacement(
            provider=judge_provider,
            expected_action=current_stage.judge_expected_action,
            technician_action=action,
        )

        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=DriveModuleReplacementJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    step_index=current_stage.step_index,
                    expected_action=current_stage.judge_expected_action,
                    technician_action=action,
                    judge_match=judgment.match,
                    judge_explanation=judgment.explanation,
                )
            )

        if judgment.match:
            reveal = await world.perform_replacement()
            return f"{REPLACEMENT_ACCEPTED_MARKER}. {reveal}"
        return (
            f"{REPLACEMENT_INEFFECTIVE_MARKER}. The replacement was not accepted — either it "
            "does not match the current required replacement, or it could not be read "
            "unambiguously as a complete, plain-language procedure. Recheck the unit, component, "
            "and every step and parameter with the engineers, and state them explicitly, in full."
        )

    return [
        ScenarioMcpTool(
            name=SERVICE_COMPONENT_TOOL,
            description=(
                "Service the next required component on the drive module: carry out its "
                "full replacement procedure. Describe exactly what you are doing — the "
                "component and every step with its parameters (tool, torque, passes, "
                "calibration). Components must be serviced in the engineer's order; "
                "only the current required component is accepted."
            ),
            executor=service_component,
        ),
    ]
