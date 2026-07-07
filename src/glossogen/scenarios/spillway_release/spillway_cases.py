"""Procedural per-round case generation for the spillway_release scenario.

A case fixes one round's reservoir crisis: the wall-clock ``current_time``
(shared with all agents), the operator's private ``start_level``, civil
defense's private ``inflow`` + qualitative ``forecast_conditions``, and the
ranger's private park schedule (``park_opens_at_hours`` / ``park_lockable``
/ ``visitors``).

Every round is one of four archetypes that exercise a distinct correct
play, sampled per round from the caller's ``archetype_weights``:

- ``hold``       — level stays in band with no release; correct play is to
  open zero gates and clear nothing.
- ``time_it``    — a release is required but the park opens later and the
  shed fits before opening; correct play releases early, clears nothing.
- ``keep_closed``— a release is required while the park is already open and
  closure is permitted; correct play has the ranger close the park.
- ``evacuate``   — a release is required while the park is already open and
  the park is committed (not closeable); correct play evacuates.

Rounds named in ``easy_round_numbers`` are forced to ``hold``. Each round is
built from an independent per-round RNG keyed on ``(seed, round_number)``,
so toggling one round never perturbs another round's case under a fixed
seed.
"""

import random
from typing import NamedTuple

from glossogen.scenarios.spillway_release.knobs import ARCHETYPE_ORDER


class SpillwayCase(NamedTuple):
    """A single spillway_release case presented for one round."""

    case_number: int
    current_time_hours: float
    start_level: int
    inflow: int
    forecast_conditions: str
    park_opens_at_hours: float | None
    park_lockable: bool
    visitors: int
    day_end_hours: float
    gate_count: int
    release_per_gate_per_hour: int
    max_level: int
    min_level: int
    round_time_budget_seconds: int


class _CaseParams(NamedTuple):
    """The per-round variable fields produced by an archetype builder."""

    current_time_hours: float
    start_level: int
    inflow: int
    forecast_conditions: str
    park_opens_at_hours: float | None
    park_lockable: bool
    visitors: int


def format_hours(value: float) -> str:
    """Render an hour-of-day float (e.g. ``8.5``) as a ``HH:MM`` clock string."""
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    return f"{hours:02d}:{minutes:02d}"


def _forecast_phrase(rng: random.Random, inflow: int) -> str:
    """Return a qualitative weather phrase consistent with ``inflow`` magnitude."""
    if inflow == 0:
        options = [
            "Clear skies, no precipitation expected.",
            "Dry and settled all day; no meaningful runoff.",
        ]
    elif inflow <= 15:
        options = [
            "Light scattered showers; modest runoff into the reservoir.",
            "Patchy drizzle easing by afternoon; small inflow.",
        ]
    elif inflow <= 35:
        options = [
            "Steady rain through much of the day; moderate inflow building.",
            "Persistent rain band overhead; sustained moderate inflow.",
        ]
    else:
        options = [
            "Heavy rain and an incoming storm front; large inflow expected.",
            "Severe downpour upstream; a major surge of inflow is coming.",
        ]
    return rng.choice(options)


def _build_hold(
    rng: random.Random,
    gate_count: int,
    release_per_gate_per_hour: int,
    max_level: int,
    min_level: int,
    day_end_hours: float,
) -> _CaseParams:
    """Calm round: holding (zero gates) keeps the level comfortably in band."""
    _ = gate_count, release_per_gate_per_hour, day_end_hours
    current_time = float(rng.choice([6, 7, 8, 9, 10]))
    start_level = rng.randint(max(min_level + 10, 40), max_level - 20)
    headroom = max_level - start_level
    inflow = rng.randint(0, min(headroom - 5, 25))
    park_opens_at, park_lockable, visitors = _sample_park(rng=rng, current_time=current_time)
    return _CaseParams(
        current_time_hours=current_time,
        start_level=start_level,
        inflow=inflow,
        forecast_conditions=_forecast_phrase(rng=rng, inflow=inflow),
        park_opens_at_hours=park_opens_at,
        park_lockable=park_lockable,
        visitors=visitors,
    )


def _build_time_it(
    rng: random.Random,
    gate_count: int,
    release_per_gate_per_hour: int,
    max_level: int,
    min_level: int,
    day_end_hours: float,
) -> _CaseParams:
    """Release required, but the park opens later and the shed fits before opening."""
    _ = min_level
    current_time = float(rng.choice([6, 7, 8, 9]))
    pre_open = float(rng.choice([2, 3, 4]))
    park_opens_at = min(current_time + pre_open, day_end_hours - 1.0)
    pre_open_hours = park_opens_at - current_time
    max_shed_before_open = int(gate_count * release_per_gate_per_hour * pre_open_hours)
    start_level = rng.randint(max(min_level + 25, 55), max_level - 20)
    excess = rng.randint(8, min(max_shed_before_open, 48))
    inflow = (max_level - start_level) + excess
    return _CaseParams(
        current_time_hours=current_time,
        start_level=start_level,
        inflow=inflow,
        forecast_conditions=_forecast_phrase(rng=rng, inflow=inflow),
        park_opens_at_hours=park_opens_at,
        park_lockable=rng.choice([True, False]),
        visitors=rng.randint(50, 200),
    )


def _build_occupied_release(
    rng: random.Random,
    gate_count: int,
    release_per_gate_per_hour: int,
    max_level: int,
    min_level: int,
    day_end_hours: float,
    park_lockable: bool,
) -> _CaseParams:
    """Release required while the park is already open; clearing is forced.

    Used for both ``keep_closed`` (``park_lockable=True``) and ``evacuate``
    (``park_lockable=False``) archetypes.
    """
    _ = min_level
    current_time = float(rng.choice([9, 10, 11, 12, 13]))
    open_offset = float(rng.choice([1, 2, 3]))
    park_opens_at = max(current_time - open_offset, 6.0)
    start_level = rng.randint(max(min_level + 25, 55), max_level - 18)
    remaining_hours = day_end_hours - current_time
    max_shed = int(gate_count * release_per_gate_per_hour * remaining_hours)
    excess = rng.randint(10, min(max_shed - 5, 45))
    inflow = (max_level - start_level) + excess
    if park_lockable:
        visitors = rng.randint(80, 300)
    else:
        visitors = rng.randint(150, 400)
    return _CaseParams(
        current_time_hours=current_time,
        start_level=start_level,
        inflow=inflow,
        forecast_conditions=_forecast_phrase(rng=rng, inflow=inflow),
        park_opens_at_hours=park_opens_at,
        park_lockable=park_lockable,
        visitors=visitors,
    )


def _sample_park(rng: random.Random, current_time: float) -> tuple[float | None, bool, int]:
    """Sample a park schedule for a round whose correct play needs no clearing.

    Returns ``(park_opens_at_hours, park_lockable, visitors)``. The park may
    be closed all day, already open, or scheduled to open later; lockability
    and visitor count are sampled but do not affect the correct (no-clear)
    play on these rounds.
    """
    choice = rng.choice(["closed_all_day", "open_now", "opens_later"])
    if choice == "closed_all_day":
        return None, rng.choice([True, False]), 0
    if choice == "open_now":
        opened_at = max(current_time - rng.choice([1, 2, 3]), 6.0)
        return opened_at, rng.choice([True, False]), rng.randint(30, 200)
    opens_at = current_time + rng.choice([2, 3, 4])
    return opens_at, rng.choice([True, False]), rng.randint(30, 200)


def _build_params_for_archetype(
    archetype: str,
    rng: random.Random,
    gate_count: int,
    release_per_gate_per_hour: int,
    max_level: int,
    min_level: int,
    day_end_hours: float,
) -> _CaseParams:
    """Dispatch to the builder for ``archetype``."""
    if archetype == "hold":
        return _build_hold(
            rng=rng,
            gate_count=gate_count,
            release_per_gate_per_hour=release_per_gate_per_hour,
            max_level=max_level,
            min_level=min_level,
            day_end_hours=day_end_hours,
        )
    if archetype == "time_it":
        return _build_time_it(
            rng=rng,
            gate_count=gate_count,
            release_per_gate_per_hour=release_per_gate_per_hour,
            max_level=max_level,
            min_level=min_level,
            day_end_hours=day_end_hours,
        )
    if archetype == "keep_closed":
        return _build_occupied_release(
            rng=rng,
            gate_count=gate_count,
            release_per_gate_per_hour=release_per_gate_per_hour,
            max_level=max_level,
            min_level=min_level,
            day_end_hours=day_end_hours,
            park_lockable=True,
        )
    if archetype == "evacuate":
        return _build_occupied_release(
            rng=rng,
            gate_count=gate_count,
            release_per_gate_per_hour=release_per_gate_per_hour,
            max_level=max_level,
            min_level=min_level,
            day_end_hours=day_end_hours,
            park_lockable=False,
        )
    raise ValueError(f"unknown archetype: {archetype}")


def get_cases(
    seed: int,
    round_count: int,
    round_time_budget_seconds: int,
    easy_round_numbers: frozenset[int],
    gate_count: int,
    release_per_gate_per_hour: int,
    max_level: int,
    min_level: int,
    day_end_hours: float,
    archetype_weights: list[int],
) -> list[SpillwayCase]:
    """Generate per-round spillway cases deterministically.

    Rounds named in ``easy_round_numbers`` are forced to the ``hold``
    archetype; every other round draws an archetype from
    ``archetype_weights`` (positional, matching
    :data:`glossogen.scenarios.spillway_release.knobs.ARCHETYPE_ORDER`). Each
    round is built from an independent RNG keyed on ``(seed, round_number)``.
    """
    cases: list[SpillwayCase] = []
    for case_index in range(round_count):
        case_number = case_index + 1
        round_rng = random.Random(f"{seed}-{case_number}")
        drawn_archetype = round_rng.choices(list(ARCHETYPE_ORDER), weights=archetype_weights, k=1)[
            0
        ]
        if case_number in easy_round_numbers:
            archetype = "hold"
        else:
            archetype = drawn_archetype
        params = _build_params_for_archetype(
            archetype=archetype,
            rng=round_rng,
            gate_count=gate_count,
            release_per_gate_per_hour=release_per_gate_per_hour,
            max_level=max_level,
            min_level=min_level,
            day_end_hours=day_end_hours,
        )
        cases.append(
            SpillwayCase(
                case_number=case_number,
                current_time_hours=params.current_time_hours,
                start_level=params.start_level,
                inflow=params.inflow,
                forecast_conditions=params.forecast_conditions,
                park_opens_at_hours=params.park_opens_at_hours,
                park_lockable=params.park_lockable,
                visitors=params.visitors,
                day_end_hours=day_end_hours,
                gate_count=gate_count,
                release_per_gate_per_hour=release_per_gate_per_hour,
                max_level=max_level,
                min_level=min_level,
                round_time_budget_seconds=round_time_budget_seconds,
            )
        )
    return cases
