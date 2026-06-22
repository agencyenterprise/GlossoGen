"""Procedural per-round case generation for the container_yard_stacking scenario.

A case is a list of steps. Each step describes one container that must be
delivered into the yard this round: the incoming container's ID (visible
only to the yard operator, and only one at a time), the target slot for
that container, the truck commits the yard operator must dispatch for
that container, and the ordered crane plan. The active crane stations and
the four-stack initial layout are round-scoped: the stack layout evolves
across the round as containers are placed and blockers are evicted.

Rounds named in ``easy_round_numbers`` are bootstrapped to a single step
so agents learn the basic deliver / lift protocol before facing
multi-container coordination. Every other round draws its per-round step
count from the caller-supplied ``step_count_values`` / ``step_count_weights``
distribution. Each round is built from an independent per-round RNG, so
toggling a round's easy status never shifts the case stream for any other
round under a fixed seed. Blocker steps - target tier already occupied -
are sampled independently per step against ``_BLOCKER_STEP_FRACTION``.
"""

import random
from typing import NamedTuple

from schmidt.scenarios.container_yard_stacking.events import ContainerYardCraneMoveStep
from schmidt.scenarios.container_yard_stacking.ids import (
    INBOUND_TRUCK_ROLE,
    OUTBOUND_TRUCK_ROLE,
    PADS_PER_STATION,
    STACK_COUNT,
    STACK_HEIGHT,
)


class StackPosition(NamedTuple):
    """A slot in the yard expressed as (stack, tier)."""

    stack: int
    tier: int


class CraneStation(NamedTuple):
    """A crane station active this round and the stack indices it can reach.

    Each station has multiple named transfer pads. Trucks park at specific
    pads; the crane reaches every pad of its own station.
    """

    station_name: str
    pads: tuple[str, ...]
    reachable_stacks: tuple[int, ...]


class TruckAssignment(NamedTuple):
    """One truck the yard operator must commit for the current step.

    ``truck_role`` is either ``inbound`` (delivers this step's incoming
    container) or ``outbound`` (arrives empty, leaves carrying the
    blocker on a blocker step). ``container_id`` is the container the
    truck must be carrying on arrival (the incoming container for
    inbound, empty string for outbound).
    """

    truck_role: str
    station_name: str
    container_id: str


class ManifestEntry(NamedTuple):
    """One entry in the shift manifest the logistics planner sees.

    The planner's injection lists every real incoming entry for the round
    mixed with several decoys so the planner cannot pick which scheduled
    container is on the current inbound truck without the yard operator's
    container ID.
    """

    container_id: str
    target_position: StackPosition


class CaseStep(NamedTuple):
    """One container delivery within a round."""

    step_index: int
    incoming_container_id: str
    target_position: StackPosition
    correct_crane_station: str
    truck_assignments: tuple[TruckAssignment, ...]
    expected_move_sequence: tuple[ContainerYardCraneMoveStep, ...]


class YardCase(NamedTuple):
    """A single container_yard_stacking case presented per round."""

    case_number: int
    active_crane_stations: tuple[CraneStation, ...]
    initial_stacks: dict[int, tuple[str, ...]]
    round_time_budget_seconds: int
    steps: tuple[CaseStep, ...]
    manifest: tuple[ManifestEntry, ...]


_CONTAINER_PREFIXES: list[str] = [
    "Orion",
    "Harbor",
    "Ridge",
    "Aurora",
    "Cobalt",
    "Vector",
    "Meridian",
    "Tundra",
    "Spire",
    "Lattice",
]

_CRANE_STATION_NAMES: list[str] = [
    "crane_station_one",
    "crane_station_two",
    "crane_station_three",
    "crane_station_four",
]

_PAD_LABELS: list[str] = [
    "north_pad",
    "south_pad",
    "east_pad",
    "west_pad",
    "inner_pad",
    "outer_pad",
]


# Per-step blocker probability. Each step independently rolls whether
# the target tier is already occupied, mirroring the previous per-round
# blocker fraction but now scoped to each container.
_BLOCKER_STEP_FRACTION = 0.4

# Fixed number of decoy manifest entries added alongside the real
# entries (one per step). Total manifest size scales with step count.
_MANIFEST_DECOY_COUNT = 3
_MAX_DECOY_SAMPLE_ATTEMPTS = 100


def _make_container_id(rng: random.Random, taken_ids: set[str]) -> str:
    """Draw one container_id unique within ``taken_ids``."""
    while True:
        prefix = rng.choice(_CONTAINER_PREFIXES)
        suffix = rng.randint(100, 999)
        container_id = f"{prefix}-{suffix}"
        if container_id not in taken_ids:
            taken_ids.add(container_id)
            return container_id


def _build_initial_stacks(
    rng: random.Random,
    step_count: int,
    taken_ids: set[str],
) -> dict[int, tuple[str, ...]]:
    """Build the four-stack initial layout for one round.

    Caps per-stack filler height so the round can place up to ``step_count``
    additional containers without exceeding ``STACK_HEIGHT``: each stack
    starts with at most ``STACK_HEIGHT`` minus a safety margin for the
    incoming containers.
    """
    max_filler = max(0, STACK_HEIGHT - 1)
    stacks: dict[int, tuple[str, ...]] = {}
    for stack_index in range(1, STACK_COUNT + 1):
        upper = min(max_filler, max(0, STACK_HEIGHT - max(1, step_count // STACK_COUNT)))
        filler_count = rng.randint(0, upper)
        fillers = [_make_container_id(rng=rng, taken_ids=taken_ids) for _ in range(filler_count)]
        stacks[stack_index] = tuple(fillers)
    return stacks


def _build_active_stations(rng: random.Random) -> tuple[CraneStation, ...]:
    """Pick 2 active crane stations with disjoint reachable-stack assignments.

    Each round produces a fresh assignment so the planner cannot memorize
    "stack X -> crane_station_y". The two stations together cover all
    ``STACK_COUNT`` stacks (``STACK_COUNT // 2`` each).
    """
    station_names = rng.sample(_CRANE_STATION_NAMES, k=2)
    pads_a = tuple(rng.sample(_PAD_LABELS, k=PADS_PER_STATION))
    remaining_pads = [label for label in _PAD_LABELS if label not in pads_a]
    pads_b = tuple(rng.sample(remaining_pads, k=PADS_PER_STATION))
    stacks = list(range(1, STACK_COUNT + 1))
    rng.shuffle(stacks)
    half = STACK_COUNT // 2
    reachable_a = tuple(sorted(stacks[:half]))
    reachable_b = tuple(sorted(stacks[half:]))
    return (
        CraneStation(
            station_name=station_names[0],
            pads=pads_a,
            reachable_stacks=reachable_a,
        ),
        CraneStation(
            station_name=station_names[1],
            pads=pads_b,
            reachable_stacks=reachable_b,
        ),
    )


def _correct_station_for_stack(stations: tuple[CraneStation, ...], target_stack: int) -> str:
    """Return the station whose ``reachable_stacks`` covers ``target_stack``."""
    for station in stations:
        if target_stack in station.reachable_stacks:
            return station.station_name
    raise ValueError(f"no active station reaches stack {target_stack}")


def _build_no_blocker_sequence(
    move_offset: int,
    incoming_container_id: str,
    target_position: StackPosition,
) -> tuple[ContainerYardCraneMoveStep, ...]:
    """One-move plan: inbound truck -> target tier."""
    return (
        ContainerYardCraneMoveStep(
            move_index=move_offset + 1,
            container_id=incoming_container_id,
            source_kind="inbound_truck",
            source_stack=None,
            source_tier=None,
            destination_kind="stack_tier",
            destination_stack=target_position.stack,
            destination_tier=target_position.tier,
        ),
    )


def _build_blocker_sequence(
    move_offset: int,
    incoming_container_id: str,
    blocker_container_id: str,
    target_position: StackPosition,
) -> tuple[ContainerYardCraneMoveStep, ...]:
    """Two-move plan: lift the blocker, then place the incoming container."""
    return (
        ContainerYardCraneMoveStep(
            move_index=move_offset + 1,
            container_id=blocker_container_id,
            source_kind="stack_tier",
            source_stack=target_position.stack,
            source_tier=target_position.tier,
            destination_kind="outbound_truck",
            destination_stack=None,
            destination_tier=None,
        ),
        ContainerYardCraneMoveStep(
            move_index=move_offset + 2,
            container_id=incoming_container_id,
            source_kind="inbound_truck",
            source_stack=None,
            source_tier=None,
            destination_kind="stack_tier",
            destination_stack=target_position.stack,
            destination_tier=target_position.tier,
        ),
    )


def _pick_target_for_step(
    rng: random.Random,
    current_stacks: dict[int, list[str]],
) -> tuple[StackPosition, bool]:
    """Pick a (target_position, has_blocker) pair valid against ``current_stacks``.

    Rolls ``_BLOCKER_STEP_FRACTION`` first, then picks a stack that can
    satisfy that mode. Falls back to the other mode if no stack can.
    Raises if the yard has neither an occupied tier nor any free tier
    (which is impossible given ``_build_initial_stacks`` caps + step
    count, but the check keeps generation honest).
    """
    prefer_blocker = rng.random() < _BLOCKER_STEP_FRACTION
    occupied = [s for s, contents in current_stacks.items() if len(contents) >= 1]
    free = [s for s, contents in current_stacks.items() if len(contents) < STACK_HEIGHT]
    if prefer_blocker and len(occupied) == 0:
        prefer_blocker = False
    if (not prefer_blocker) and len(free) == 0:
        prefer_blocker = True
    if prefer_blocker:
        if len(occupied) == 0:
            raise ValueError("yard is completely empty AND completely full; cannot continue")
        stack = rng.choice(occupied)
        tier = len(current_stacks[stack])
        return StackPosition(stack=stack, tier=tier), True
    stack = rng.choice(free)
    tier = len(current_stacks[stack]) + 1
    return StackPosition(stack=stack, tier=tier), False


def _build_steps(
    rng: random.Random,
    step_count: int,
    active_stations: tuple[CraneStation, ...],
    initial_stacks: dict[int, tuple[str, ...]],
    taken_ids: set[str],
) -> tuple[tuple[CaseStep, ...], dict[int, list[str]]]:
    """Build the per-step plan, mutating a simulated stack state as we go.

    Returns both the steps and the final simulated stack state, so the
    caller can size manifest decoys against the post-round layout.
    """
    sim_stacks: dict[int, list[str]] = {
        stack_index: list(contents) for stack_index, contents in initial_stacks.items()
    }
    steps: list[CaseStep] = []
    move_offset = 0
    for step_index in range(1, step_count + 1):
        target_position, has_blocker = _pick_target_for_step(rng=rng, current_stacks=sim_stacks)
        incoming_container_id = _make_container_id(rng=rng, taken_ids=taken_ids)
        correct_station_name = _correct_station_for_stack(
            stations=active_stations, target_stack=target_position.stack
        )
        inbound_assignment = TruckAssignment(
            truck_role=INBOUND_TRUCK_ROLE,
            station_name=correct_station_name,
            container_id=incoming_container_id,
        )
        truck_assignments: tuple[TruckAssignment, ...]
        expected_moves: tuple[ContainerYardCraneMoveStep, ...]
        if has_blocker:
            blocker_container_id = sim_stacks[target_position.stack][-1]
            outbound_assignment = TruckAssignment(
                truck_role=OUTBOUND_TRUCK_ROLE,
                station_name=correct_station_name,
                container_id="",
            )
            truck_assignments = (inbound_assignment, outbound_assignment)
            expected_moves = _build_blocker_sequence(
                move_offset=move_offset,
                incoming_container_id=incoming_container_id,
                blocker_container_id=blocker_container_id,
                target_position=target_position,
            )
            sim_stacks[target_position.stack].pop()  # blocker leaves on outbound truck
            sim_stacks[target_position.stack].append(incoming_container_id)
        else:
            truck_assignments = (inbound_assignment,)
            expected_moves = _build_no_blocker_sequence(
                move_offset=move_offset,
                incoming_container_id=incoming_container_id,
                target_position=target_position,
            )
            sim_stacks[target_position.stack].append(incoming_container_id)
        move_offset += len(expected_moves)
        steps.append(
            CaseStep(
                step_index=step_index,
                incoming_container_id=incoming_container_id,
                target_position=target_position,
                correct_crane_station=correct_station_name,
                truck_assignments=truck_assignments,
                expected_move_sequence=expected_moves,
            )
        )
    return tuple(steps), sim_stacks


def _sample_decoy_targets(
    rng: random.Random,
    final_stacks: dict[int, list[str]],
    forbidden_positions: set[tuple[int, int]],
    count: int,
) -> list[StackPosition]:
    """Draw ``count`` distinct decoy target slots compatible with the layout.

    Decoys are sampled against the post-round stack state so they remain
    structurally plausible (occupied tier for blocker decoys, next-empty
    tier for no-blocker decoys). Each decoy independently rolls the same
    blocker probability as a real step.
    """
    forbidden: set[tuple[int, int]] = set(forbidden_positions)
    decoys: list[StackPosition] = []
    attempts = 0
    while len(decoys) < count and attempts < _MAX_DECOY_SAMPLE_ATTEMPTS:
        attempts += 1
        stack = rng.randint(1, STACK_COUNT)
        height = len(final_stacks[stack])
        decoy_has_blocker = rng.random() < _BLOCKER_STEP_FRACTION
        if decoy_has_blocker:
            if height < 1:
                continue
            tier = rng.randint(1, height)
        else:
            if height >= STACK_HEIGHT:
                continue
            tier = height + 1
        key = (stack, tier)
        if key in forbidden:
            continue
        forbidden.add(key)
        decoys.append(StackPosition(stack=stack, tier=tier))
    return decoys


def _build_manifest(
    rng: random.Random,
    steps: tuple[CaseStep, ...],
    final_stacks: dict[int, list[str]],
    taken_ids: set[str],
) -> tuple[ManifestEntry, ...]:
    """Build the shuffled manifest: every real step entry plus decoys."""
    forbidden_positions: set[tuple[int, int]] = {
        (step.target_position.stack, step.target_position.tier) for step in steps
    }
    decoy_targets = _sample_decoy_targets(
        rng=rng,
        final_stacks=final_stacks,
        forbidden_positions=forbidden_positions,
        count=_MANIFEST_DECOY_COUNT,
    )
    decoys = [
        ManifestEntry(
            container_id=_make_container_id(rng=rng, taken_ids=taken_ids),
            target_position=target,
        )
        for target in decoy_targets
    ]
    real_entries = [
        ManifestEntry(
            container_id=step.incoming_container_id,
            target_position=step.target_position,
        )
        for step in steps
    ]
    entries = real_entries + decoys
    rng.shuffle(entries)
    return tuple(entries)


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
    step_count_values: list[int],
    step_count_weights: list[int],
) -> list[YardCase]:
    """Generate per-round container yard cases deterministically.

    Rounds named in ``easy_round_numbers`` are forced to a single
    delivery; every other round's step count is drawn from
    ``step_count_values`` weighted by ``step_count_weights``. Each round is
    built from an independent per-round RNG seeded from
    ``(seed, round_number)``, so a round's case content depends only on
    the seed and that round's own configuration: toggling one round in or
    out of ``easy_round_numbers`` (or any other per-round change) never
    perturbs any other round's case. Each step independently rolls a
    blocker against ``_BLOCKER_STEP_FRACTION``. Container IDs are unique
    within each round.
    """
    cases: list[YardCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        drawn_step_count = round_rng.choices(step_count_values, weights=step_count_weights, k=1)[0]
        if case_number in easy_round_numbers:
            step_count = 1
        else:
            step_count = drawn_step_count
        cases.append(
            _build_one_case(
                rng=round_rng,
                case_number=case_number,
                step_count=step_count,
                round_time_budget_seconds=round_time_budget_seconds,
                taken_ids=set(),
            )
        )
    return cases


def _build_one_case(
    rng: random.Random,
    case_number: int,
    step_count: int,
    round_time_budget_seconds: int,
    taken_ids: set[str],
) -> YardCase:
    """Generate one multi-step yard case end-to-end.

    ``taken_ids`` tracks container IDs already drawn within this round so
    the case has no duplicate containers; callers pass a fresh set per
    round.
    """
    initial_stacks = _build_initial_stacks(rng=rng, step_count=step_count, taken_ids=taken_ids)
    active_stations = _build_active_stations(rng=rng)
    steps, final_stacks = _build_steps(
        rng=rng,
        step_count=step_count,
        active_stations=active_stations,
        initial_stacks=initial_stacks,
        taken_ids=taken_ids,
    )
    manifest = _build_manifest(
        rng=rng,
        steps=steps,
        final_stacks=final_stacks,
        taken_ids=taken_ids,
    )
    return YardCase(
        case_number=case_number,
        active_crane_stations=active_stations,
        initial_stacks=initial_stacks,
        round_time_budget_seconds=round_time_budget_seconds,
        steps=steps,
        manifest=manifest,
    )
