"""Deterministic truck-commit and crane-move judging for the yard world.

Each function takes the single ``TeamState`` it judges against (the world
chooses which team based on the calling agent), the round's
``YardCase``/``CaseStep`` ground truth, and the ``WorldContext`` used to
broadcast per-team notifications on the link channel. All scoring is
deterministic — no LLM judge — so the only failure modes are mismatches
between the parsed tool arguments and the ground-truth assignments or
the current physical state of the yard.
"""

from schmidt.runtime.scenario_world import WorldContext
from schmidt.scenarios.container_yard_stacking.events import ContainerYardCraneMoveStep
from schmidt.scenarios.container_yard_stacking.ids import (
    CONTAINER_PLACED_MARKER,
    INBOUND_TRUCK_ROLE,
    OUTBOUND_TRUCK_ROLE,
    TRUCK_ARRIVED_MARKER,
    TRUCK_WRONG_SPOT_MARKER,
)
from schmidt.scenarios.container_yard_stacking.world_state import (
    StepOutcome,
    TeamState,
    TruckCommitResult,
    TruckState,
    stack_position_text,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import CaseStep, TruckAssignment

NEXT_CONTAINER_MARKER = "NEXT INCOMING CONTAINER"


def find_assignment(current_step: CaseStep | None, truck_role: str) -> TruckAssignment | None:
    """Return the ground-truth assignment for ``truck_role`` on the current step."""
    if current_step is None:
        return None
    for assignment in current_step.truck_assignments:
        if assignment.truck_role == truck_role:
            return assignment
    return None


def pads_already_committed(team: TeamState) -> list[str]:
    """Return non-empty pads currently bound to an arrived truck for this team's step."""
    return [state.pad for state in team.truck_states.values() if state.arrived and state.pad != ""]


def source_holds_container(
    team: TeamState, kind: str, stack: int | None, container_id: str
) -> bool:
    """Return True when the named source currently carries ``container_id``."""
    if kind == "inbound_truck":
        state = team.truck_states.get(INBOUND_TRUCK_ROLE)
        return state is not None and state.arrived and state.container_id == container_id
    if kind == "outbound_truck":
        state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
        return state is not None and state.arrived and state.container_id == container_id
    if kind == "stack_tier":
        if stack is None or stack not in team.current_stacks:
            return False
        contents = team.current_stacks[stack]
        return len(contents) > 0 and contents[-1] == container_id
    return False


def destination_is_free(team: TeamState, kind: str, stack: int | None, tier: int | None) -> bool:
    """Return True when the named destination is free for a crane drop."""
    if kind == "inbound_truck":
        return False
    if kind == "outbound_truck":
        state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
        return state is not None and state.arrived and state.container_id == ""
    if kind == "stack_tier":
        if stack is None or stack not in team.current_stacks or tier is None:
            return False
        return tier == len(team.current_stacks[stack]) + 1
    return False


def last_failure_reason(team: TeamState) -> str:
    """Return the team's most recently recorded failure reason for this round."""
    if team.failure_reason == "":
        return "Crane move rejected."
    return team.failure_reason


async def record_truck_commit(
    team: TeamState,
    current_step: CaseStep | None,
    context: WorldContext,
    parsed_truck_role: str,
    parsed_pad: str,
    role_matches_active_assignment: bool,
    targets_correct_station: bool,
    targets_correct_pad: bool,
    carries_correct_container: bool,
) -> TruckCommitResult:
    """Update the team's state with the verdict for one ``move_truck`` call."""
    if current_step is None:
        return TruckCommitResult(
            truck_role=parsed_truck_role,
            accepted=False,
            duplicate=False,
        )
    if parsed_truck_role in team.truck_states:
        return TruckCommitResult(
            truck_role=parsed_truck_role,
            accepted=False,
            duplicate=True,
        )
    assignment = find_assignment(current_step=current_step, truck_role=parsed_truck_role)
    pad_already_used = parsed_pad != "" and parsed_pad in pads_already_committed(team=team)
    role_known = assignment is not None
    all_correct = (
        role_matches_active_assignment
        and targets_correct_station
        and targets_correct_pad
        and carries_correct_container
        and role_known
        and not pad_already_used
    )
    if not all_correct:
        team.round_failed_terminally = True
        reason = _truck_failure_reason(
            parsed_truck_role=parsed_truck_role,
            role_matches_active_assignment=role_matches_active_assignment,
            targets_correct_station=targets_correct_station,
            targets_correct_pad=targets_correct_pad,
            carries_correct_container=carries_correct_container,
            role_known=role_known,
            pad_already_used=pad_already_used,
        )
        if team.failure_reason == "":
            team.failure_reason = reason
        team.truck_states[parsed_truck_role] = TruckState(
            truck_role=parsed_truck_role,
            arrived=False,
            station_name="",
            pad="",
            container_id="",
        )
        await context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text=f"{parsed_truck_role.upper()} {TRUCK_WRONG_SPOT_MARKER}. {reason}",
        )
        return TruckCommitResult(
            truck_role=parsed_truck_role,
            accepted=False,
            duplicate=False,
        )
    accepted_assignment = assignment
    assert accepted_assignment is not None
    team.truck_states[parsed_truck_role] = TruckState(
        truck_role=parsed_truck_role,
        arrived=True,
        station_name=accepted_assignment.station_name,
        pad=parsed_pad,
        container_id=accepted_assignment.container_id,
    )
    team.step_correctly_committed_truck_count += 1
    await context.send_update_to_channel(
        channel_id=team.link_channel_id,
        text=(
            f"{parsed_truck_role.upper()} {TRUCK_ARRIVED_MARKER}. The truck is "
            f"positioned at {accepted_assignment.station_name}, {parsed_pad} and is ready "
            "for the crane."
        ),
    )
    return TruckCommitResult(
        truck_role=parsed_truck_role,
        accepted=True,
        duplicate=False,
    )


async def record_crane_move(
    team: TeamState,
    current_step: CaseStep | None,
    next_step: CaseStep | None,
    context: WorldContext,
    parsed_move: ContainerYardCraneMoveStep,
    parsed_source_kind: str,
    parsed_source_stack: int | None,
    parsed_destination_kind: str,
    parsed_destination_stack: int | None,
    matches_expected_next_move: bool,
    source_currently_holds_container: bool,
    destination_currently_empty: bool,
) -> bool:
    """Apply or reject a crane move for ``team`` and emit a notification.

    Returns True if the move was accepted. The caller passes ``next_step``
    so this module can broadcast the next round's incoming container ID
    on advance without re-deriving the world's case map.
    """
    if current_step is None:
        return False
    round_already_failed = team.round_failed_terminally
    sequence_already_exhausted = team.step_accepted_move_count >= len(
        current_step.expected_move_sequence
    )
    structural_invariant_holds = _structural_invariants_hold(
        team=team,
        container_id=parsed_move.container_id,
        source_kind=parsed_source_kind,
        source_stack=parsed_source_stack,
        destination_kind=parsed_destination_kind,
        destination_stack=parsed_destination_stack,
    )
    accepted = (
        matches_expected_next_move
        and source_currently_holds_container
        and destination_currently_empty
        and not round_already_failed
        and not sequence_already_exhausted
        and structural_invariant_holds
    )
    if not accepted:
        team.round_failed_terminally = True
        reason = _crane_failure_reason(
            matches_expected_next_move=matches_expected_next_move,
            source_currently_holds_container=source_currently_holds_container,
            destination_currently_empty=destination_currently_empty,
            round_already_failed=round_already_failed,
            sequence_already_exhausted=sequence_already_exhausted,
            structural_invariant_holds=structural_invariant_holds,
        )
        if team.failure_reason == "":
            team.failure_reason = reason
        return False
    _apply_move_to_state(
        team=team,
        parsed_move=parsed_move,
        source_kind=parsed_source_kind,
        source_stack=parsed_source_stack,
        destination_kind=parsed_destination_kind,
        destination_stack=parsed_destination_stack,
    )
    team.step_accepted_move_count += 1
    if _incoming_container_at_target_for_step(team=team, step=current_step):
        target_text = stack_position_text(
            stack=current_step.target_position.stack,
            tier=current_step.target_position.tier,
        )
        await context.send_update_to_channel(
            channel_id=team.link_channel_id,
            text=(
                f"{CONTAINER_PLACED_MARKER}. {current_step.incoming_container_id} "
                f"is now at {target_text}."
            ),
        )
        await _advance_step(
            team=team,
            completed_step=current_step,
            next_step=next_step,
            context=context,
        )
    return True


async def _advance_step(
    team: TeamState,
    completed_step: CaseStep,
    next_step: CaseStep | None,
    context: WorldContext,
) -> None:
    """Close the team's current step and reveal the next step's incoming container."""
    team.step_outcomes.append(
        StepOutcome(
            step_index=completed_step.step_index,
            incoming_container_id=completed_step.incoming_container_id,
            target_position_text=stack_position_text(
                stack=completed_step.target_position.stack,
                tier=completed_step.target_position.tier,
            ),
            succeeded=True,
            expected_move_count=len(completed_step.expected_move_sequence),
            accepted_move_count=team.step_accepted_move_count,
            expected_truck_count=len(completed_step.truck_assignments),
            correctly_committed_truck_count=team.step_correctly_committed_truck_count,
        )
    )
    team.current_step_index += 1
    team.truck_states = {}
    team.step_accepted_move_count = 0
    team.step_correctly_committed_truck_count = 0
    if next_step is not None:
        await context.send_update_to_agent(
            agent_id=team.yard_operator_id,
            text=(
                f"{NEXT_CONTAINER_MARKER}: {next_step.incoming_container_id}. "
                "Share this with the planner the same way you shared the first."
            ),
        )


def _structural_invariants_hold(
    team: TeamState,
    container_id: str,
    source_kind: str,
    source_stack: int | None,
    destination_kind: str,
    destination_stack: int | None,
) -> bool:
    """Verify the parsed move's structural invariants against the live team state."""
    if source_kind == "outbound_truck":
        return False
    if destination_kind == "inbound_truck":
        return False
    if source_kind == "inbound_truck":
        state = team.truck_states.get(INBOUND_TRUCK_ROLE)
        if state is None or not state.arrived or state.container_id != container_id:
            return False
    elif source_kind == "stack_tier":
        if source_stack is None or source_stack not in team.current_stacks:
            return False
        stack_contents = team.current_stacks[source_stack]
        if len(stack_contents) == 0 or stack_contents[-1] != container_id:
            return False
    else:
        return False
    if destination_kind == "outbound_truck":
        state = team.truck_states.get(OUTBOUND_TRUCK_ROLE)
        if state is None or not state.arrived or state.container_id != "":
            return False
    elif destination_kind == "stack_tier":
        if destination_stack is None or destination_stack not in team.current_stacks:
            return False
    else:
        return False
    return True


def _incoming_container_at_target_for_step(team: TeamState, step: CaseStep) -> bool:
    """Return True when ``step``'s incoming container has reached its target slot."""
    stack_contents = team.current_stacks.get(step.target_position.stack)
    if stack_contents is None:
        return False
    if len(stack_contents) < step.target_position.tier:
        return False
    tier_index = step.target_position.tier - 1
    return stack_contents[tier_index] == step.incoming_container_id


def _apply_move_to_state(
    team: TeamState,
    parsed_move: ContainerYardCraneMoveStep,
    source_kind: str,
    source_stack: int | None,
    destination_kind: str,
    destination_stack: int | None,
) -> None:
    """Mutate the team's stack and truck state to reflect an accepted move."""
    container_id = parsed_move.container_id
    if source_kind == "inbound_truck":
        _unload_truck(team=team, truck_role=INBOUND_TRUCK_ROLE)
    elif source_kind == "stack_tier":
        assert source_stack is not None
        team.current_stacks[source_stack].pop()
    if destination_kind == "outbound_truck":
        _load_truck(team=team, truck_role=OUTBOUND_TRUCK_ROLE, container_id=container_id)
    elif destination_kind == "stack_tier":
        assert destination_stack is not None
        team.current_stacks[destination_stack].append(container_id)


def _unload_truck(team: TeamState, truck_role: str) -> None:
    """Mark ``truck_role`` as empty on ``team``."""
    state = team.truck_states.get(truck_role)
    if state is None:
        return
    team.truck_states[truck_role] = state._replace(container_id="")


def _load_truck(team: TeamState, truck_role: str, container_id: str) -> None:
    """Mark ``truck_role`` as carrying ``container_id`` on ``team``."""
    state = team.truck_states.get(truck_role)
    if state is None:
        return
    team.truck_states[truck_role] = state._replace(container_id=container_id)


def _truck_failure_reason(
    parsed_truck_role: str,
    role_matches_active_assignment: bool,
    targets_correct_station: bool,
    targets_correct_pad: bool,
    carries_correct_container: bool,
    role_known: bool,
    pad_already_used: bool,
) -> str:
    """Build a specific failure-reason string from the truck verdict's per-criterion booleans.

    When ``role_matches_active_assignment`` is False there is no assignment
    to compare the station/pad/container against, so the other booleans
    default to False and would produce a misleading cascade of reasons.
    The function short-circuits in that case with one root-cause string.
    """
    prefix = f"{parsed_truck_role} truck did not arrive at the correct spot"
    if not role_matches_active_assignment:
        if role_known:
            return f"{prefix}: role does not match any active assignment for this step."
        return f"{prefix}: no assignment matches the parsed role {parsed_truck_role!r}."
    reasons: list[str] = []
    if not targets_correct_station:
        reasons.append("destination text does not identify the correct crane station")
    if not targets_correct_pad:
        reasons.append("destination pad is not a free pad at the correct station")
    if not carries_correct_container:
        if parsed_truck_role == "outbound":
            reasons.append(
                "outbound truck must declare an empty container_id "
                "(it leaves loaded by a later lift_from_stack call)"
            )
        else:
            reasons.append("container_id does not match the assignment's incoming container")
    if pad_already_used:
        reasons.append("destination pad is already used by another truck this step")
    if not reasons:
        return f"{prefix}."
    return f"{prefix}: " + "; ".join(reasons) + "."


def _crane_failure_reason(
    matches_expected_next_move: bool,
    source_currently_holds_container: bool,
    destination_currently_empty: bool,
    round_already_failed: bool,
    sequence_already_exhausted: bool,
    structural_invariant_holds: bool,
) -> str:
    """Build a specific failure-reason string from the crane verdict's per-criterion booleans.

    Short-circuit on root-cause conditions so we don't cascade the
    move-correctness reasons (which become uninformative or misleading
    once the round is already over, the step's sequence is done, or
    the parsed input doesn't refer to anything in the live world state).
    """
    prefix = "Crane move rejected"
    if round_already_failed:
        return f"{prefix}: round was already terminally failed before this move."
    if sequence_already_exhausted:
        return f"{prefix}: all expected moves for this step have already been executed."
    if not structural_invariant_holds:
        return f"{prefix}: parsed source/destination did not match the live world state."
    reasons: list[str] = []
    if not matches_expected_next_move:
        reasons.append("move did not match the expected next step")
    if not source_currently_holds_container:
        reasons.append("source does not currently hold the named container")
    if not destination_currently_empty:
        reasons.append("destination is not currently empty")
    if not reasons:
        return f"{prefix}."
    return f"{prefix}: " + "; ".join(reasons) + "."
