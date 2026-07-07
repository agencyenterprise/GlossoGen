"""Procedural per-round case generation for the container_yard_stacking scenario.

Each round a batch of containers arrives in the yard's intake slots; each
must be relocated to an assigned target bay. A container has no ID — it is a
bundle of attributes (colour, size, type, marking). The full batch is known
at round start: the spotter sees each container's attributes and intake slot,
the planner sees each container's attributes and target bay, the crane sees
only slot occupancy. Neither describer alone holds both a container's intake
slot and its target bay, so the team must join their reports on the
container's attributes — under a per-round-resampled assignment that cannot
be memorized.

Each round is built from an independent per-round RNG seeded from
``(seed, round_number)``, so a round's content depends only on the seed and
that round's own configuration.
"""

import logging
import random
from typing import NamedTuple

from glossogen.scenarios.container_yard_stacking.container_attributes import (
    ATTRIBUTE_NAMES,
    ATTRIBUTE_VALUES,
    Container,
)

logger = logging.getLogger(__name__)

_MAX_DRAW_ATTEMPTS = 10000


class CaseStep(NamedTuple):
    """One container relocation within a round: from its intake slot to its target bay."""

    step_index: int
    container: Container
    intake_slot: int
    target_slot: int


class YardCase(NamedTuple):
    """A single container_yard_stacking case presented per round."""

    case_number: int
    round_time_budget_seconds: int
    yard_slot_count: int
    initial_row: dict[int, Container | None]
    steps: tuple[CaseStep, ...]


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
    batch_size_values: list[int],
    batch_size_weights: list[int],
    yard_slot_count: int,
) -> list[YardCase]:
    """Generate per-round yard cases deterministically from ``seed``."""
    cases: list[YardCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        drawn = round_rng.choices(batch_size_values, weights=batch_size_weights, k=1)[0]
        if case_number in easy_round_numbers:
            batch_size = 1
        else:
            batch_size = drawn
        cases.append(
            _build_one_case(
                rng=round_rng,
                case_number=case_number,
                batch_size=batch_size,
                round_time_budget_seconds=round_time_budget_seconds,
                yard_slot_count=yard_slot_count,
            )
        )
    return cases


def _build_one_case(
    rng: random.Random,
    case_number: int,
    batch_size: int,
    round_time_budget_seconds: int,
    yard_slot_count: int,
) -> YardCase:
    """Generate one batch case: distinct containers, intake slots, disjoint target bays."""
    containers = _draw_distinct_containers(rng=rng, count=batch_size)
    # Intake slots and target bays are disjoint, so every move is an
    # independent intake -> empty-bay relocation with no blockers.
    slots = rng.sample(range(1, yard_slot_count + 1), k=2 * batch_size)
    intake_slots = slots[:batch_size]
    target_slots = slots[batch_size:]
    initial_row: dict[int, Container | None] = {
        slot: None for slot in range(1, yard_slot_count + 1)
    }
    steps: list[CaseStep] = []
    for index, container in enumerate(containers):
        intake_slot = intake_slots[index]
        target_slot = target_slots[index]
        initial_row[intake_slot] = container
        steps.append(
            CaseStep(
                step_index=index + 1,
                container=container,
                intake_slot=intake_slot,
                target_slot=target_slot,
            )
        )
    return YardCase(
        case_number=case_number,
        round_time_budget_seconds=round_time_budget_seconds,
        yard_slot_count=yard_slot_count,
        initial_row=initial_row,
        steps=tuple(steps),
    )


def _draw_distinct_containers(rng: random.Random, count: int) -> list[Container]:
    """Draw ``count`` containers with distinct full attribute bundles."""
    seen: set[Container] = set()
    out: list[Container] = []
    attempts = 0
    while len(out) < count and attempts < _MAX_DRAW_ATTEMPTS:
        attempts += 1
        values = tuple(rng.choice(ATTRIBUTE_VALUES[name]) for name in ATTRIBUTE_NAMES)
        container = Container(values=values)
        if container in seen:
            continue
        seen.add(container)
        out.append(container)
    return out
