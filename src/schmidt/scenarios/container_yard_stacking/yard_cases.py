"""Procedural per-round case generation for the container_yard_stacking scenario.

A case bundles every piece of dynamic per-round state the agents need to
coordinate: the incoming container's manifest (visible only to the yard
operator), the active crane stations and which stacks they reach (visible
only to the logistics planner), the current four-stack layout (visible only
to the planner), the correct truck destination, the target position for the
incoming container, the available temp holding slots, and the ordered crane
plan the world will validate the crane operator's moves against. Two
difficulty levels are produced: easy cases need a single crane move
(truck -> target tier on top of an empty or partial stack), hard cases
need two moves (one blocker container is relocated to a temp slot, then
the incoming container is placed at the now-uncovered target tier).
"""

import random
from typing import NamedTuple

from schmidt.scenarios.container_yard_stacking.ids import (
    BAY_NAME,
    BLOCK_NAME,
    STACK_COUNT,
    STACK_HEIGHT,
    TEMP_SLOT_NAMES,
)


class Container(NamedTuple):
    """The incoming container's manifest as the yard operator sees it."""

    container_id: str
    size_class: str
    weight_tons: float
    departure_group: str


class StackPosition(NamedTuple):
    """A slot in the yard expressed as block / bay / stack / tier."""

    block: str
    bay: str
    stack: int
    tier: int


class CraneStation(NamedTuple):
    """A crane station active this round and the stack indices it can reach."""

    station_name: str
    transfer_pad: str
    reachable_stacks: tuple[int, ...]


class CraneMoveStep(NamedTuple):
    """One step of the expected crane plan, in canonical source/destination strings."""

    move_index: int
    container_id: str
    source: str
    destination: str


class YardCase(NamedTuple):
    """A single container_yard_stacking case presented per round."""

    case_number: int
    incoming_container: Container
    active_crane_stations: tuple[CraneStation, ...]
    correct_crane_station: str
    correct_transfer_pad: str
    initial_stacks: dict[int, tuple[str, ...]]
    target_position: StackPosition
    temp_slot_names: tuple[str, ...]
    expected_move_sequence: tuple[CraneMoveStep, ...]
    time_budget_seconds: int


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

_SIZE_CLASSES: list[str] = [
    "forty-foot high-cube",
    "forty-foot standard",
    "twenty-foot standard",
]

_DEPARTURE_GROUPS: list[str] = [
    "north departure group",
    "south departure group",
    "east departure group",
    "west departure group",
]

_CRANE_STATION_NAMES: list[str] = [
    "Crane Station One",
    "Crane Station Two",
    "Crane Station Three",
    "Crane Station Four",
]

_TRANSFER_PADS: list[str] = [
    "east transfer pad",
    "west transfer pad",
    "north transfer pad",
    "south transfer pad",
]


def _make_container(rng: random.Random, prefix_taken: set[str]) -> Container:
    """Draw one container with a unique container_id."""
    while True:
        prefix = rng.choice(_CONTAINER_PREFIXES)
        suffix = rng.randint(100, 999)
        container_id = f"{prefix}-{suffix}"
        if container_id not in prefix_taken:
            prefix_taken.add(container_id)
            return Container(
                container_id=container_id,
                size_class=rng.choice(_SIZE_CLASSES),
                weight_tons=round(rng.uniform(5.0, 32.0), 1),
                departure_group=rng.choice(_DEPARTURE_GROUPS),
            )


def _build_initial_stacks(
    rng: random.Random,
    target_stack: int,
    target_stack_height: int,
    prefix_taken: set[str],
) -> dict[int, tuple[str, ...]]:
    """Build the four-stack initial layout for one round.

    The target stack starts with exactly ``target_stack_height`` filler
    containers stacked from tier 1 upward. The other stacks get a random 0-2
    fillers each. The caller decides how to use that pre-existing top of
    stack — either place the incoming container on top of it (easy) or
    relocate the top container first and reuse its tier (hard).
    """
    stacks: dict[int, tuple[str, ...]] = {}
    for stack_index in range(1, STACK_COUNT + 1):
        if stack_index == target_stack:
            fillers = [
                _make_container(rng=rng, prefix_taken=prefix_taken).container_id
                for _ in range(target_stack_height)
            ]
            stacks[stack_index] = tuple(fillers)
        else:
            filler_count = rng.randint(0, 2)
            fillers = [
                _make_container(rng=rng, prefix_taken=prefix_taken).container_id
                for _ in range(filler_count)
            ]
            stacks[stack_index] = tuple(fillers)
    return stacks


def _stack_position_string(position: StackPosition) -> str:
    """Render a StackPosition into the canonical text used in expected moves."""
    return f"{position.block}, {position.bay}, " f"Stack {position.stack}, Tier {position.tier}"


def _truck_source_string(station_name: str, transfer_pad: str) -> str:
    """Render the canonical source string for a container still on the truck."""
    return f"truck at {station_name}, {transfer_pad}"


def _build_active_stations(
    rng: random.Random,
    target_stack: int,
) -> tuple[tuple[CraneStation, ...], str, str]:
    """Pick 2 active crane stations with disjoint reachable-stack assignments.

    Each round produces a fresh assignment so the planner cannot memorize
    "stack X -> Crane Station Y". The station that reaches ``target_stack``
    is the correct one.
    """
    station_names = rng.sample(_CRANE_STATION_NAMES, k=2)
    pads = rng.sample(_TRANSFER_PADS, k=2)
    stacks = list(range(1, STACK_COUNT + 1))
    rng.shuffle(stacks)
    half = STACK_COUNT // 2
    reachable_a = tuple(sorted(stacks[:half]))
    reachable_b = tuple(sorted(stacks[half:]))
    stations = (
        CraneStation(
            station_name=station_names[0],
            transfer_pad=pads[0],
            reachable_stacks=reachable_a,
        ),
        CraneStation(
            station_name=station_names[1],
            transfer_pad=pads[1],
            reachable_stacks=reachable_b,
        ),
    )
    if target_stack in reachable_a:
        return stations, station_names[0], pads[0]
    return stations, station_names[1], pads[1]


def _build_easy_sequence(
    incoming_container_id: str,
    target_position: StackPosition,
    truck_source: str,
) -> tuple[CraneMoveStep, ...]:
    """Build the one-move plan for an easy case: truck -> target tier."""
    return (
        CraneMoveStep(
            move_index=1,
            container_id=incoming_container_id,
            source=truck_source,
            destination=_stack_position_string(position=target_position),
        ),
    )


def _build_hard_sequence(
    incoming_container_id: str,
    blocker_container_id: str,
    target_position: StackPosition,
    truck_source: str,
    chosen_temp_slot: str,
) -> tuple[CraneMoveStep, ...]:
    """Build the two-move plan for a hard case.

    Move the topmost blocker (currently at ``target_position.tier``) to a
    free temp holding slot, then place the incoming container at the tier
    the blocker just vacated.
    """
    target_text = _stack_position_string(position=target_position)
    return (
        CraneMoveStep(
            move_index=1,
            container_id=blocker_container_id,
            source=target_text,
            destination=chosen_temp_slot,
        ),
        CraneMoveStep(
            move_index=2,
            container_id=incoming_container_id,
            source=truck_source,
            destination=target_text,
        ),
    )


def get_cases(
    seed: int,
    round_count: int,
    time_budget_seconds: int,
    hard_case_fraction: float,
) -> list[YardCase]:
    """Generate per-round container yard cases deterministically.

    Each round picks: an incoming container, four-stack initial layout,
    target slot, two active crane stations with fresh disjoint
    reachable-stack assignments, the correct station, the temp slot the
    crane plan will use, and the resulting one- or two-step expected crane
    move sequence.
    """
    rng = random.Random(seed)
    cases: list[YardCase] = []
    for case_index in range(round_count):
        cases.append(
            _build_one_case(
                rng=rng,
                case_number=case_index + 1,
                hard_case_fraction=hard_case_fraction,
                time_budget_seconds=time_budget_seconds,
            )
        )
    return cases


def _build_one_case(
    rng: random.Random,
    case_number: int,
    hard_case_fraction: float,
    time_budget_seconds: int,
) -> YardCase:
    """Generate one yard case end-to-end."""
    prefix_taken: set[str] = set()
    incoming = _make_container(rng=rng, prefix_taken=prefix_taken)
    is_hard = rng.random() < hard_case_fraction
    target_stack = rng.randint(1, STACK_COUNT)
    if is_hard:
        target_stack_height = rng.randint(1, STACK_HEIGHT - 1)
        target_tier = target_stack_height
    else:
        target_stack_height = rng.randint(0, STACK_HEIGHT - 1)
        target_tier = target_stack_height + 1
    initial_stacks = _build_initial_stacks(
        rng=rng,
        target_stack=target_stack,
        target_stack_height=target_stack_height,
        prefix_taken=prefix_taken,
    )
    target_position = StackPosition(
        block=BLOCK_NAME,
        bay=BAY_NAME,
        stack=target_stack,
        tier=target_tier,
    )
    active_stations, correct_station, correct_pad = _build_active_stations(
        rng=rng,
        target_stack=target_stack,
    )
    truck_source = _truck_source_string(
        station_name=correct_station,
        transfer_pad=correct_pad,
    )
    if is_hard:
        blocker_container_id = initial_stacks[target_stack][-1]
        chosen_temp_slot = rng.choice(TEMP_SLOT_NAMES)
        expected_sequence = _build_hard_sequence(
            incoming_container_id=incoming.container_id,
            blocker_container_id=blocker_container_id,
            target_position=target_position,
            truck_source=truck_source,
            chosen_temp_slot=chosen_temp_slot,
        )
    else:
        expected_sequence = _build_easy_sequence(
            incoming_container_id=incoming.container_id,
            target_position=target_position,
            truck_source=truck_source,
        )
    return YardCase(
        case_number=case_number,
        incoming_container=incoming,
        active_crane_stations=active_stations,
        correct_crane_station=correct_station,
        correct_transfer_pad=correct_pad,
        initial_stacks=initial_stacks,
        target_position=target_position,
        temp_slot_names=tuple(TEMP_SLOT_NAMES),
        expected_move_sequence=expected_sequence,
        time_budget_seconds=time_budget_seconds,
    )
