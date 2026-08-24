"""Where a fork cuts the source log, and how many rounds it plays after.

``resolve_fork_boundary`` picks the truncation anchor for a fork after round N:
the source's ``RoundAdvanced(N+1)`` when one exists, or the last event before
``SimulationEnded`` when round N was the source's final round.
``resolve_rounds_after`` turns the CLI's ``--rounds-after`` into the stored
manifest window.
"""

from datetime import UTC, datetime, timedelta

import pytest

from glossogen.models.event import (
    RoundAdvanced,
    RoundEnded,
    RunStatus,
    SimulationEnded,
    SimulationEvent,
    SimulationStarted,
)
from glossogen.models.event_base import EventBase
from glossogen.replace_agent import (
    find_boundary_timestamp,
    resolve_fork_boundary,
    resolve_rounds_after,
)

_START = datetime(2026, 8, 1, tzinfo=UTC)


def _stamp(events: list[SimulationEvent]) -> list[SimulationEvent]:
    """Give each event a distinct increasing timestamp, in list order."""
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        base = event
        assert isinstance(base, EventBase)
        stamped.append(base.model_copy(update={"timestamp": _START + timedelta(seconds=index)}))
    return stamped


def _started() -> SimulationStarted:
    """A minimal SimulationStarted, present so index 0 is never the boundary."""
    return SimulationStarted(
        round_number=0,
        run_id="smoke/1",
        scenario_name="smoke",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 3},
        provider="anthropic",
    )


def _source_with_rounds_past_the_boundary() -> list[SimulationEvent]:
    """A source that advanced into round 3, so a fork after round 2 re-opens it."""
    return _stamp(
        [
            _started(),
            RoundAdvanced(round_number=1, trigger="initial"),
            RoundAdvanced(round_number=2, trigger="all_agents_idle"),
            RoundAdvanced(round_number=3, trigger="all_agents_idle"),
        ]
    )


def _completed_source(final_round: int) -> list[SimulationEvent]:
    """A source that finished at ``final_round`` and recorded its end."""
    return _ended_source(final_round=final_round, reason=RunStatus.SCENARIO_COMPLETE)


def _ended_source(final_round: int, reason: RunStatus) -> list[SimulationEvent]:
    """A source that stopped at ``final_round`` with the given end reason."""
    events: list[SimulationEvent] = [_started()]
    for round_number in range(1, final_round + 1):
        events.append(RoundAdvanced(round_number=round_number, trigger="all_agents_idle"))
    events.append(RoundEnded(round_number=final_round, trigger="all_agents_idle"))
    events.append(
        SimulationEnded(
            round_number=final_round,
            reason=reason,
            total_messages=4,
            total_cost_usd=0.0,
        )
    )
    return _stamp(events)


def test_a_fork_before_the_source_end_anchors_on_the_entry_rounds_advance() -> None:
    """The clone keeps rounds 1..N closed with round N+1 opened but uninjected."""
    events = _source_with_rounds_past_the_boundary()

    boundary = resolve_fork_boundary(events=events, after_round=2)

    entry_advance = events[3]
    assert boundary.target_event_id == entry_advance.event_id
    assert boundary.boundary_timestamp == entry_advance.timestamp
    assert boundary.advances_into_round is False


def test_a_fork_after_the_final_round_anchors_just_before_simulation_ended() -> None:
    """No RoundAdvanced exists past the boundary, so the clone ends before the end marker."""
    events = _completed_source(final_round=2)

    boundary = resolve_fork_boundary(events=events, after_round=2)

    last_before_ended = events[-2]
    assert isinstance(events[-1], SimulationEnded)
    assert boundary.target_event_id == last_before_ended.event_id
    assert boundary.advances_into_round is True


def test_a_killed_source_cannot_be_forked_after_its_final_round() -> None:
    """A kill can land mid-round, so the last round is not a completed boundary."""
    events = _ended_source(final_round=2, reason=RunStatus.KILLED)

    with pytest.raises(ValueError, match=r"ended with reason 'killed', so round 2 may be"):
        resolve_fork_boundary(events=events, after_round=2)


def test_a_killed_then_resumed_source_anchors_after_the_resumed_segment() -> None:
    """A mid-log end marker from a recovered crash does not move the boundary."""
    events = _stamp(
        [
            _started(),
            RoundAdvanced(round_number=1, trigger="all_agents_idle"),
            RoundAdvanced(round_number=2, trigger="all_agents_idle"),
            SimulationEnded(
                round_number=2,
                reason=RunStatus.KILLED,
                total_messages=2,
                total_cost_usd=0.0,
            ),
            RoundEnded(round_number=2, trigger="all_agents_idle"),
            SimulationEnded(
                round_number=2,
                reason=RunStatus.SCENARIO_COMPLETE,
                total_messages=4,
                total_cost_usd=0.0,
            ),
        ]
    )

    boundary = resolve_fork_boundary(events=events, after_round=2)

    resumed_round_end = events[-2]
    assert isinstance(resumed_round_end, RoundEnded)
    assert boundary.target_event_id == resumed_round_end.event_id
    assert boundary.advances_into_round is True


def test_a_boundary_below_one_is_refused() -> None:
    """Rounds start at 1; replaying from the very beginning is a fresh run, not a fork."""
    with pytest.raises(ValueError, match=r"--after-round must be >= 1"):
        resolve_fork_boundary(events=_completed_source(final_round=2), after_round=0)


def test_a_round_the_source_never_reached_is_refused_with_the_last_round_named() -> None:
    """The error tells the caller how far the source actually got."""
    with pytest.raises(
        ValueError,
        match=r"source run never completed round 5: last round advanced was 3",
    ):
        resolve_fork_boundary(events=_source_with_rounds_past_the_boundary(), after_round=5)


def test_a_round_the_source_opened_but_never_finished_is_refused() -> None:
    """An interrupted source has no completed boundary at its last round."""
    events = _source_with_rounds_past_the_boundary()

    with pytest.raises(ValueError, match=r"opened round 3 but never finished it"):
        resolve_fork_boundary(events=events, after_round=3)


def test_find_boundary_timestamp_returns_the_named_events_timestamp() -> None:
    """Downstream helpers filter the source timeline by this timestamp."""
    events = _completed_source(final_round=2)

    assert (
        find_boundary_timestamp(
            events=events,
            target_event_id=events[2].event_id,
        )
        == events[2].timestamp
    )


def test_find_boundary_timestamp_refuses_an_unknown_event_id() -> None:
    """A missing anchor means the clone and its manifest disagree."""
    with pytest.raises(ValueError, match=r"No event with event_id='ghost'"):
        find_boundary_timestamp(events=_completed_source(final_round=2), target_event_id="ghost")


def test_an_explicit_rounds_after_stores_one_less() -> None:
    """K new rounds land as the manifest window round_count - entry_round = K - 1."""
    stored = resolve_rounds_after(
        after_round=2,
        rounds_after=3,
        knob_round_count=None,
        source_scenario_config={"round_count": 3},
    )

    assert stored == 2


def test_rounds_after_below_one_is_refused() -> None:
    """A fork that plays no rounds is not a fork."""
    with pytest.raises(ValueError, match=r"--rounds-after must be >= 1"):
        resolve_rounds_after(
            after_round=2,
            rounds_after=0,
            knob_round_count=None,
            source_scenario_config={"round_count": 3},
        )


def test_the_default_replays_the_source_rounds_past_the_boundary() -> None:
    """round_count 5 forked after round 2 plays rounds 3..5, stored window 2."""
    stored = resolve_rounds_after(
        after_round=2,
        rounds_after=None,
        knob_round_count=None,
        source_scenario_config={"round_count": 5},
    )

    assert stored == 2


def test_a_final_round_fork_requires_an_explicit_rounds_after() -> None:
    """Past the source's end there is nothing to replay, so no default exists."""
    with pytest.raises(
        ValueError,
        match=r"source run ends at round 2; --after-round 2 leaves no source rounds",
    ):
        resolve_rounds_after(
            after_round=2,
            rounds_after=None,
            knob_round_count=None,
            source_scenario_config={"round_count": 2},
        )


def test_a_source_config_without_round_count_cannot_default() -> None:
    """The default reads the source's round_count; without it the caller must be explicit."""
    with pytest.raises(ValueError, match=r"no integer 'round_count' entry"):
        resolve_rounds_after(
            after_round=2,
            rounds_after=None,
            knob_round_count=None,
            source_scenario_config={},
        )


def test_a_preset_round_count_sets_the_forks_total_rounds() -> None:
    """Every shipped preset carries round_count; passed via --knobs it is the target."""
    stored = resolve_rounds_after(
        after_round=14,
        rounds_after=None,
        knob_round_count=25,
        source_scenario_config={"round_count": 15},
    )

    assert stored == 10


def test_a_knob_round_count_agreeing_with_rounds_after_is_accepted() -> None:
    """A preset naming the same total as the flag is not a conflict."""
    stored = resolve_rounds_after(
        after_round=14,
        rounds_after=11,
        knob_round_count=25,
        source_scenario_config={"round_count": 15},
    )

    assert stored == 10


def test_a_knob_round_count_disagreeing_with_rounds_after_is_refused() -> None:
    """Two sources of the same number must not silently pick a winner."""
    with pytest.raises(ValueError, match=r"--rounds-after 11 and the --knobs round_count 30"):
        resolve_rounds_after(
            after_round=14,
            rounds_after=11,
            knob_round_count=30,
            source_scenario_config={"round_count": 15},
        )


def test_a_knob_round_count_at_or_below_the_boundary_is_refused() -> None:
    """A preset whose round_count equals the source's end forces an explicit choice."""
    with pytest.raises(ValueError, match=r"round_count 15 leaves no rounds past --after-round 15"):
        resolve_rounds_after(
            after_round=15,
            rounds_after=None,
            knob_round_count=15,
            source_scenario_config={"round_count": 15},
        )
