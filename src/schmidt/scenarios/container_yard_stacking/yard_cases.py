"""Procedural per-round case generation for the container_yard_stacking scenario.

A case bundles every piece of dynamic per-round state the agents need to
coordinate: the incoming container's ID (visible only to the yard
operator), the active crane stations and which stacks they reach (visible
only to the logistics planner), the current four-stack layout (visible only
to the planner), the target position for the incoming container, the truck
assignments the yard operator must commit, and the ordered crane plan the
world will validate the crane operator's moves against. Two difficulty
levels are produced: easy cases need a single inbound truck and one crane
move (truck -> target tier on top of an empty or partial stack); hard cases
need both an inbound and an outbound truck plus two crane moves (one
blocker container is lifted from the target tier onto the outbound truck,
then the incoming container is placed at the now-uncovered tier).
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
    """A slot in the yard expressed as block / bay / stack / tier."""

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
    """One truck the yard operator must commit this round.

    ``truck_role`` is either ``inbound`` (delivers the incoming container)
    or ``outbound`` (arrives empty, leaves carrying a blocker on hard
    cases). ``station_name`` is the truck's correct station;
    ``container_id`` is the container the truck must be carrying on
    arrival (the incoming container for inbound, empty string for
    outbound). The transfer pad is the planner's choice at runtime — any
    pad of the correct station is acceptable, with the constraint that
    inbound and outbound trucks must use different pads on hard rounds.
    """

    truck_role: str
    station_name: str
    container_id: str


class ManifestEntry(NamedTuple):
    """One entry in the shift manifest the logistics planner sees.

    The planner's injection lists the real incoming entry together with
    several decoys so the planner cannot pick which container is on the
    inbound truck (and therefore which target slot the round actually
    requires) without the yard operator's container ID.
    """

    container_id: str
    target_position: StackPosition


class YardCase(NamedTuple):
    """A single container_yard_stacking case presented per round."""

    case_number: int
    incoming_container_id: str
    active_crane_stations: tuple[CraneStation, ...]
    correct_crane_station: str
    initial_stacks: dict[int, tuple[str, ...]]
    target_position: StackPosition
    truck_assignments: tuple[TruckAssignment, ...]
    expected_move_sequence: tuple[ContainerYardCraneMoveStep, ...]
    time_budget_seconds: int
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
    target_stack: int,
    target_stack_height: int,
    taken_ids: set[str],
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
                _make_container_id(rng=rng, taken_ids=taken_ids) for _ in range(target_stack_height)
            ]
            stacks[stack_index] = tuple(fillers)
        else:
            filler_count = rng.randint(0, 2)
            fillers = [
                _make_container_id(rng=rng, taken_ids=taken_ids) for _ in range(filler_count)
            ]
            stacks[stack_index] = tuple(fillers)
    return stacks


def _build_active_stations(
    rng: random.Random,
    target_stack: int,
) -> tuple[tuple[CraneStation, ...], str]:
    """Pick 2 active crane stations with disjoint reachable-stack assignments.

    Each round produces a fresh assignment so the planner cannot memorize
    "stack X -> crane_station_y". Each station has ``PADS_PER_STATION``
    freshly named pads. The station that reaches ``target_stack`` is the
    correct one for both trucks.
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
    stations = (
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
    if target_stack in reachable_a:
        return stations, station_names[0]
    return stations, station_names[1]


def _build_easy_sequence(
    incoming_container_id: str,
    target_position: StackPosition,
) -> tuple[ContainerYardCraneMoveStep, ...]:
    """Build the one-move plan for an easy case: inbound truck -> target tier."""
    return (
        ContainerYardCraneMoveStep(
            move_index=1,
            container_id=incoming_container_id,
            source_kind="inbound_truck",
            source_stack=None,
            source_tier=None,
            destination_kind="stack_tier",
            destination_stack=target_position.stack,
            destination_tier=target_position.tier,
        ),
    )


def _build_hard_sequence(
    incoming_container_id: str,
    blocker_container_id: str,
    target_position: StackPosition,
) -> tuple[ContainerYardCraneMoveStep, ...]:
    """Build the two-move plan for a hard case.

    Lift the topmost blocker (currently at ``target_position.tier``) onto
    the outbound truck, then lift the incoming container off the inbound
    truck onto the tier the blocker just vacated.
    """
    return (
        ContainerYardCraneMoveStep(
            move_index=1,
            container_id=blocker_container_id,
            source_kind="stack_tier",
            source_stack=target_position.stack,
            source_tier=target_position.tier,
            destination_kind="outbound_truck",
            destination_stack=None,
            destination_tier=None,
        ),
        ContainerYardCraneMoveStep(
            move_index=2,
            container_id=incoming_container_id,
            source_kind="inbound_truck",
            source_stack=None,
            source_tier=None,
            destination_kind="stack_tier",
            destination_stack=target_position.stack,
            destination_tier=target_position.tier,
        ),
    )


# Round difficulty is not a user knob. A fixed proportion of rounds
# carries a blocker on the target tier; the rest are blocker-free. The
# order is shuffled per seed so agents can't predict which rounds will be
# hard ahead of time, but the count is deterministic for a given
# ``round_count`` so cross-seed comparisons stay comparable.
_HARD_ROUND_FRACTION = 0.4

# Decoys added to the planner's manifest alongside the real entry. The
# decoys' targets are independently sampled with the same blocker
# probability so the planner cannot infer the active entry from
# "which one happens to have a blocker".
_MANIFEST_DECOY_COUNT = 3
_MAX_DECOY_SAMPLE_ATTEMPTS = 100


def _sample_decoy_targets(
    rng: random.Random,
    initial_stacks: dict[int, tuple[str, ...]],
    real_target: StackPosition,
    count: int,
) -> list[StackPosition]:
    """Draw ``count`` distinct decoy target slots compatible with the layout.

    Each decoy independently rolls the same blocker probability as a
    real case, so blocker/no-blocker decoys appear in the same mix as
    real cases. Decoys must point at structurally valid slots (an
    occupied tier for blocker decoys, or the next-empty tier for
    no-blocker decoys) so the planner cannot rule them out as
    impossible.
    """
    forbidden: set[tuple[int, int]] = {(real_target.stack, real_target.tier)}
    decoys: list[StackPosition] = []
    attempts = 0
    while len(decoys) < count and attempts < _MAX_DECOY_SAMPLE_ATTEMPTS:
        attempts += 1
        stack = rng.randint(1, STACK_COUNT)
        height = len(initial_stacks[stack])
        decoy_has_blocker = rng.random() < _HARD_ROUND_FRACTION
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
    incoming_container_id: str,
    target_position: StackPosition,
    initial_stacks: dict[int, tuple[str, ...]],
    taken_ids: set[str],
) -> tuple[ManifestEntry, ...]:
    """Build the shuffled manifest: 1 real entry + ``_MANIFEST_DECOY_COUNT`` decoys."""
    decoy_targets = _sample_decoy_targets(
        rng=rng,
        initial_stacks=initial_stacks,
        real_target=target_position,
        count=_MANIFEST_DECOY_COUNT,
    )
    decoys = [
        ManifestEntry(
            container_id=_make_container_id(rng=rng, taken_ids=taken_ids),
            target_position=target,
        )
        for target in decoy_targets
    ]
    entries = [
        ManifestEntry(container_id=incoming_container_id, target_position=target_position),
        *decoys,
    ]
    rng.shuffle(entries)
    return tuple(entries)


def get_cases(
    seed: int,
    round_count: int,
    time_budget_seconds: int,
) -> list[YardCase]:
    """Generate per-round container yard cases deterministically.

    A fixed fraction of rounds (``_HARD_ROUND_FRACTION``) carries a
    blocker on the target tier; the rest are blocker-free. The difficulty
    sequence is built deterministically and then shuffled by the seeded
    RNG, so each seed sees a different running order but the same total
    blocker count.

    Each round picks: an incoming container, four-stack initial layout,
    target slot, two active crane stations with fresh disjoint
    reachable-stack assignments and fresh pad names, the correct station,
    the inbound truck assignment (plus an outbound assignment when the
    round has a blocker), and the resulting one- or two-step expected
    crane move sequence. Container IDs are unique across the full run so
    a shorthand like ``Orion-742`` always refers to the same container.
    """
    rng = random.Random(seed)
    hard_count = round(_HARD_ROUND_FRACTION * round_count)
    difficulties: list[bool] = [True] * hard_count + [False] * (round_count - hard_count)
    rng.shuffle(difficulties)
    cases: list[YardCase] = []
    taken_ids: set[str] = set()
    for case_index in range(round_count):
        cases.append(
            _build_one_case(
                rng=rng,
                case_number=case_index + 1,
                has_blocker=difficulties[case_index],
                time_budget_seconds=time_budget_seconds,
                taken_ids=taken_ids,
            )
        )
    return cases


class _TruckPlan(NamedTuple):
    """The truck assignments and the expected crane move sequence for one case."""

    truck_assignments: tuple[TruckAssignment, ...]
    expected_move_sequence: tuple[ContainerYardCraneMoveStep, ...]


def _build_truck_plan(
    has_blocker: bool,
    incoming_container_id: str,
    initial_stacks: dict[int, tuple[str, ...]],
    target_position: StackPosition,
    correct_station_name: str,
) -> _TruckPlan:
    """Build the truck assignments and the structured crane move sequence."""
    inbound_assignment = TruckAssignment(
        truck_role=INBOUND_TRUCK_ROLE,
        station_name=correct_station_name,
        container_id=incoming_container_id,
    )
    if not has_blocker:
        return _TruckPlan(
            truck_assignments=(inbound_assignment,),
            expected_move_sequence=_build_easy_sequence(
                incoming_container_id=incoming_container_id,
                target_position=target_position,
            ),
        )
    outbound_assignment = TruckAssignment(
        truck_role=OUTBOUND_TRUCK_ROLE,
        station_name=correct_station_name,
        container_id="",
    )
    blocker_container_id = initial_stacks[target_position.stack][-1]
    return _TruckPlan(
        truck_assignments=(inbound_assignment, outbound_assignment),
        expected_move_sequence=_build_hard_sequence(
            incoming_container_id=incoming_container_id,
            blocker_container_id=blocker_container_id,
            target_position=target_position,
        ),
    )


def _target_tier_for_case(rng: random.Random, has_blocker: bool) -> tuple[int, int]:
    """Return ``(target_stack_height, target_tier)`` consistent with the round's blocker state.

    Rounds with a blocker cover tiers ``1..STACK_HEIGHT`` (a fully-stacked
    target is a valid blocker configuration: the blocker at the top must
    be moved aside). Rounds without a blocker cover tiers
    ``1..STACK_HEIGHT`` by placing the incoming container on top of
    ``0..STACK_HEIGHT-1`` pre-existing fillers.
    """
    if has_blocker:
        target_stack_height = rng.randint(1, STACK_HEIGHT)
        return target_stack_height, target_stack_height
    target_stack_height = rng.randint(0, STACK_HEIGHT - 1)
    return target_stack_height, target_stack_height + 1


def _build_one_case(
    rng: random.Random,
    case_number: int,
    has_blocker: bool,
    time_budget_seconds: int,
    taken_ids: set[str],
) -> YardCase:
    """Generate one yard case end-to-end."""
    incoming_container_id = _make_container_id(rng=rng, taken_ids=taken_ids)
    target_stack = rng.randint(1, STACK_COUNT)
    target_stack_height, target_tier = _target_tier_for_case(rng=rng, has_blocker=has_blocker)
    initial_stacks = _build_initial_stacks(
        rng=rng,
        target_stack=target_stack,
        target_stack_height=target_stack_height,
        taken_ids=taken_ids,
    )
    target_position = StackPosition(stack=target_stack, tier=target_tier)
    active_stations, correct_station_name = _build_active_stations(
        rng=rng,
        target_stack=target_stack,
    )
    truck_plan = _build_truck_plan(
        has_blocker=has_blocker,
        incoming_container_id=incoming_container_id,
        initial_stacks=initial_stacks,
        target_position=target_position,
        correct_station_name=correct_station_name,
    )
    manifest = _build_manifest(
        rng=rng,
        incoming_container_id=incoming_container_id,
        target_position=target_position,
        initial_stacks=initial_stacks,
        taken_ids=taken_ids,
    )
    return YardCase(
        case_number=case_number,
        incoming_container_id=incoming_container_id,
        active_crane_stations=active_stations,
        correct_crane_station=correct_station_name,
        initial_stacks=initial_stacks,
        target_position=target_position,
        truck_assignments=truck_plan.truck_assignments,
        expected_move_sequence=truck_plan.expected_move_sequence,
        time_budget_seconds=time_budget_seconds,
        manifest=manifest,
    )
