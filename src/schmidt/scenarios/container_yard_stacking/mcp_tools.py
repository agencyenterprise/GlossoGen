"""The three MCP tools the yard scenario exposes to its agents.

``move_truck`` is the yard operator's commit; ``place_on_stack`` and
``lift_from_stack`` are the crane operator's (and the intern's, after
takeover) physical moves. Each tool builds a deterministic verdict
against the round's ``YardCase`` ground truth, hands it to the
world for state mutation, and logs the verdict as a JSONL event.
"""

from typing import Callable, Literal

from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from schmidt.scenario_protocol import ScenarioRuntimeHandle
from schmidt.scenarios.container_yard_stacking.case_event_conversion import (
    correct_station_pads_for_step,
)
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCraneMoveJudged,
    ContainerYardCraneMoveStep,
    ContainerYardCraneMoveVerdict,
    ContainerYardTruckCommitVerdict,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import (
    INBOUND_TRUCK_ROLE,
    MOVE_REJECTED_MARKER,
    MOVE_SUCCESS_MARKER,
    OUTBOUND_TRUCK_ROLE,
)
from schmidt.scenarios.container_yard_stacking.injection_rendering import intern_has_taken_over
from schmidt.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from schmidt.scenarios.container_yard_stacking.team_routing import (
    role_kind_for_agent,
    team_id_for_agent,
)
from schmidt.scenarios.container_yard_stacking.world import ContainerYardWorld


def build_mcp_tools(
    world: ContainerYardWorld,
    knobs: ContainerYardStackingKnobs,
    get_runtime: Callable[[], ScenarioRuntimeHandle | None],
) -> list[ScenarioMcpTool]:
    """Return the ``move_truck`` / ``place_on_stack`` / ``lift_from_stack`` tool list."""

    async def move_truck(
        ctx: ToolContext,
        truck_role: Literal["inbound", "outbound"],
        station_name: str,
        pad: str,
        container_id: str,
    ) -> str:
        """Commit one truck (inbound or outbound) to a crane transfer pad.

        Pass the truck role, the station name, the chosen pad, and the
        container_id the truck carries (the incoming container's ID for
        inbound; empty string for outbound).
        """
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return (
                "Cannot move the truck during the post-round discussion phase. "
                "Wait for the next round to begin."
            )
        if role_kind_for_agent(agent_id=agent_id) != "yard_operator":
            return "Only the yard operator can call move_truck."
        team_id = team_id_for_agent(agent_id=agent_id)
        if world.round_failed_terminally(team_id=team_id):
            return "Round has already failed terminally; no more truck commits accepted."
        case = world.current_case
        current_step = world.current_step(team_id=team_id)
        if case is None or current_step is None:
            return "No active yard step."
        correct_station_pads = correct_station_pads_for_step(case=case, step=current_step)
        assignment = world.find_assignment(team_id=team_id, truck_role=truck_role)
        role_matches_active_assignment = assignment is not None
        targets_correct_station = assignment is not None and station_name == assignment.station_name
        pads_in_use = world.pads_already_committed(team_id=team_id)
        targets_correct_pad = pad in correct_station_pads and pad not in pads_in_use
        carries_correct_container = (
            assignment is not None and container_id == assignment.container_id
        )
        verdict = ContainerYardTruckCommitVerdict(
            role_matches_active_assignment=role_matches_active_assignment,
            targets_correct_station=targets_correct_station,
            targets_correct_pad=targets_correct_pad,
            carries_correct_container=carries_correct_container,
        )
        commit_result = await world.record_truck_commit(
            team_id=team_id,
            parsed_truck_role=truck_role,
            parsed_pad=pad,
            role_matches_active_assignment=role_matches_active_assignment,
            targets_correct_station=targets_correct_station,
            targets_correct_pad=targets_correct_pad,
            carries_correct_container=carries_correct_container,
        )
        if commit_result.duplicate:
            return f"{truck_role} truck has already been committed this round."
        if commit_result.accepted:
            assert assignment is not None
            if assignment.container_id == "":
                container_clause = ""
            else:
                container_clause = f" carrying {assignment.container_id}"
            explanation = (
                f"{truck_role} truck committed to "
                f"{assignment.station_name}, {pad}{container_clause}."
            )
        else:
            explanation = _explain_truck_rejection(verdict=verdict, truck_role=truck_role)
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=ContainerYardTruckJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    step_index=current_step.step_index,
                    submitted_truck_role=truck_role,
                    submitted_station_name=station_name,
                    submitted_pad=pad,
                    submitted_container_id=container_id,
                    verdict=verdict,
                    overall_success=commit_result.accepted,
                    explanation=explanation,
                )
            )
        if commit_result.accepted:
            return f"Accepted. {explanation} A world notification was broadcast."
        return f"Rejected. {explanation}"

    async def execute_crane_move(
        ctx: ToolContext,
        container_id: str,
        source_kind: Literal["inbound_truck", "stack_tier"],
        destination_kind: Literal["outbound_truck", "stack_tier"],
        stack: int,
        tier: int,
        tool_name: str,
    ) -> str:
        """Shared body for both crane tools.

        ``source_kind`` / ``destination_kind`` are fixed by the calling
        tool; ``stack`` / ``tier`` describe the stack_tier endpoint
        (which is the source for ``lift_from_stack`` and the destination
        for ``place_on_stack``).
        """
        agent_id = resolve_agent_id(ctx=ctx)
        if world.in_postmortem:
            return (
                "Cannot move the crane during the post-round discussion phase. "
                "Wait for the next round to begin."
            )
        role_kind = role_kind_for_agent(agent_id=agent_id)
        if role_kind == "intern":
            runtime = get_runtime()
            if runtime is None:
                current_round = 0
            else:
                current_round = runtime.current_round
            if not intern_has_taken_over(round_number=current_round, knobs=knobs):
                return (
                    f"The intern cannot call {tool_name} before the takeover round. "
                    "Continue silent observation until takeover."
                )
        elif role_kind != "crane_operator":
            return f"Only the crane operator can call {tool_name}."
        team_id = team_id_for_agent(agent_id=agent_id)
        if world.round_failed_terminally(team_id=team_id):
            return f"{MOVE_REJECTED_MARKER}. The round has already failed; no more moves accepted."
        current_step = world.current_step(team_id=team_id)
        if current_step is None:
            return f"{MOVE_REJECTED_MARKER}. No active yard step."
        next_index = world.step_accepted_move_count(team_id=team_id)
        if next_index >= len(current_step.expected_move_sequence):
            return (
                f"{MOVE_REJECTED_MARKER}. All expected crane moves for this step have "
                "already been executed."
            )
        expected_step = current_step.expected_move_sequence[next_index]
        missing_role = _next_step_missing_truck_role(
            world=world, team_id=team_id, step=expected_step
        )
        if missing_role is not None:
            return (
                f"{MOVE_REJECTED_MARKER}. The {missing_role} truck has not arrived at its "
                "spot yet. Wait for the yard operator to commit it before craning."
            )
        if source_kind == "stack_tier":
            source_stack = stack
            source_tier = tier
        else:
            source_stack = None
            source_tier = None
        if destination_kind == "stack_tier":
            destination_stack = stack
            destination_tier = tier
        else:
            destination_stack = None
            destination_tier = None
        submitted_move = ContainerYardCraneMoveStep(
            move_index=expected_step.move_index,
            container_id=container_id,
            source_kind=source_kind,
            source_stack=source_stack,
            source_tier=source_tier,
            destination_kind=destination_kind,
            destination_stack=destination_stack,
            destination_tier=destination_tier,
        )
        verdict = ContainerYardCraneMoveVerdict(
            matches_expected_next_move=(
                container_id == expected_step.container_id
                and source_kind == expected_step.source_kind
                and source_stack == expected_step.source_stack
                and source_tier == expected_step.source_tier
                and destination_kind == expected_step.destination_kind
                and destination_stack == expected_step.destination_stack
                and destination_tier == expected_step.destination_tier
            ),
            source_currently_holds_container=world.source_holds_container(
                team_id=team_id,
                kind=source_kind,
                stack=source_stack,
                container_id=container_id,
            ),
            destination_currently_empty=world.destination_is_free(
                team_id=team_id,
                kind=destination_kind,
                stack=destination_stack,
                tier=destination_tier,
            ),
            parsed_source_kind=source_kind,
            parsed_source_stack=source_stack,
            parsed_destination_kind=destination_kind,
            parsed_destination_stack=destination_stack,
        )
        accepted = await world.record_crane_move(
            team_id=team_id,
            parsed_move=submitted_move,
            parsed_source_kind=verdict.parsed_source_kind,
            parsed_source_stack=verdict.parsed_source_stack,
            parsed_destination_kind=verdict.parsed_destination_kind,
            parsed_destination_stack=verdict.parsed_destination_stack,
            matches_expected_next_move=verdict.matches_expected_next_move,
            source_currently_holds_container=verdict.source_currently_holds_container,
            destination_currently_empty=verdict.destination_currently_empty,
        )
        if accepted:
            marker = MOVE_SUCCESS_MARKER
            explanation = f"Move {expected_step.move_index} executed: {container_id}."
        else:
            marker = MOVE_REJECTED_MARKER
            explanation = world.last_failure_reason(team_id=team_id)
        runtime = get_runtime()
        if runtime is not None:
            await runtime.event_logger.log(
                event=ContainerYardCraneMoveJudged(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    step_index=current_step.step_index,
                    move_index=expected_step.move_index,
                    submitted_move=submitted_move,
                    verdict=verdict,
                    accepted=accepted,
                    marker=marker,
                    explanation=explanation,
                )
            )
        if accepted:
            return f"{MOVE_SUCCESS_MARKER}. {explanation}"
        return f"{MOVE_REJECTED_MARKER}. {explanation}"

    async def place_on_stack(
        ctx: ToolContext,
        container_id: str,
        stack: int,
        tier: int,
    ) -> str:
        """Crane: take the incoming container off the inbound truck and place it at the slot.

        ``tier`` must be the next-empty tier above the current top of
        the destination stack.
        """
        return await execute_crane_move(
            ctx=ctx,
            container_id=container_id,
            source_kind="inbound_truck",
            destination_kind="stack_tier",
            stack=stack,
            tier=tier,
            tool_name="place_on_stack",
        )

    async def lift_from_stack(
        ctx: ToolContext,
        container_id: str,
        stack: int,
        tier: int,
    ) -> str:
        """Crane: lift the container at (stack, tier) onto the outbound truck.

        ``tier`` must be the topmost occupied tier of the source stack.
        The outbound truck leaves loaded with this container.
        """
        return await execute_crane_move(
            ctx=ctx,
            container_id=container_id,
            source_kind="stack_tier",
            destination_kind="outbound_truck",
            stack=stack,
            tier=tier,
            tool_name="lift_from_stack",
        )

    return [
        ScenarioMcpTool(
            name="move_truck",
            description=(
                "Commit one truck (inbound or outbound) to a crane transfer pad. "
                "Args: truck_role ('inbound' or 'outbound'), station_name, pad, "
                "container_id (the incoming container's ID for inbound; empty "
                "string for outbound). Call once per truck per round; rounds with "
                "a blocker need both the inbound and an outbound commit."
            ),
            executor=move_truck,
        ),
        ScenarioMcpTool(
            name="place_on_stack",
            description=(
                "Crane: take the incoming container off the inbound truck and "
                "place it at the given (stack, tier). Args: container_id, stack, "
                "tier. The tier must be the next-empty tier above the destination "
                "stack's current top. Call this once on rounds without a blocker; "
                "call it after lift_from_stack on rounds with a blocker."
            ),
            executor=place_on_stack,
        ),
        ScenarioMcpTool(
            name="lift_from_stack",
            description=(
                "Crane: lift the container at (stack, tier) onto the outbound "
                "truck (which leaves loaded). Args: container_id, stack, tier. "
                "The tier must be the topmost occupied tier of the source stack. "
                "Only used on rounds where the target slot is currently occupied; "
                "call this before place_on_stack."
            ),
            executor=lift_from_stack,
        ),
    ]


def _explain_truck_rejection(verdict: ContainerYardTruckCommitVerdict, truck_role: str) -> str:
    """Build a human-readable rejection explanation from the per-criterion verdict.

    When ``role_matches_active_assignment`` is False there is no assignment
    to compare the station/pad/container against, so the other booleans
    default to False and would produce a misleading cascade of reasons.
    Short-circuit with one root-cause string in that case.
    """
    if not verdict.role_matches_active_assignment:
        return "Truck commit rejected: the submitted truck_role is not active this round."
    reasons: list[str] = []
    if not verdict.targets_correct_station:
        reasons.append("the submitted station does not match the assignment")
    if not verdict.targets_correct_pad:
        reasons.append(
            "the submitted pad is not one of the correct station's pads "
            "or is already used by another truck"
        )
    if not verdict.carries_correct_container:
        if truck_role == "outbound":
            reasons.append(
                "outbound truck must declare an empty container_id "
                "(it leaves loaded by a later lift_from_stack call)"
            )
        else:
            reasons.append("the submitted container_id does not match the assignment")
    if not reasons:
        return "Truck commit rejected."
    return "Truck commit rejected: " + "; ".join(reasons) + "."


def _next_step_missing_truck_role(
    world: ContainerYardWorld, team_id: str, step: ContainerYardCraneMoveStep
) -> str | None:
    """Return a truck role required by ``step`` that has not yet arrived for ``team_id``."""
    if step.source_kind == "inbound_truck" and not world.truck_arrived(
        team_id=team_id, truck_role=INBOUND_TRUCK_ROLE
    ):
        return INBOUND_TRUCK_ROLE
    if step.destination_kind == "outbound_truck" and not world.truck_arrived(
        team_id=team_id, truck_role=OUTBOUND_TRUCK_ROLE
    ):
        return OUTBOUND_TRUCK_ROLE
    return None
