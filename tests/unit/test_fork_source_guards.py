"""Which run directories the fork flows accept as sources.

A derived run rebuilds seats pass-through from its clone's log, so a source
whose log holds turns some seat's live agent never saw is refused: a cross-run
run always (the imported seat's real history lives in a sidecar the clone does
not carry), a replace-agent run unless the same seat is being replaced again,
and a boundary behind an already-fired in-run swap, whose filters and
swapped-in model live only in its config and ``AgentSwappedMidRun`` event.
Source B of a cross-run import, and the source of a history transfer, is judged
per seat: only the seat whose history is taken must have a clean single-agent
history in the source's log. A history-transfer run is refused as a fork source,
and its transferred seats are refused as history sources, because the history
those seats started with lives in a sidecar, not in the log.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from glossogen.models.event import AgentSwappedMidRun, SimulationEvent
from glossogen.run_derivation.replace_agent import (
    refuse_boundary_with_swapped_seats,
    refuse_seat_swapped_before_cutoff,
    refuse_seat_with_mixed_history,
    refuse_unforkable_source,
)
from glossogen.run_storage.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    IMPORTED_HISTORY_SOURCE_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.run_storage.history_transfer_manifest import (
    HistoryTransferManifest,
    TransferredSeat,
    write_history_transfer_manifest,
)
from tests.fakes.replace_manifests import write_replace_manifest

_BOUNDARY = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _swap(agent_id: str, before_boundary: bool) -> AgentSwappedMidRun:
    """An in-run swap of ``agent_id``, timestamped relative to the boundary."""
    if before_boundary:
        timestamp = _BOUNDARY - timedelta(minutes=5)
    else:
        timestamp = _BOUNDARY + timedelta(minutes=5)
    return AgentSwappedMidRun(
        round_number=10,
        agent_id=agent_id,
        new_model="claude-sonnet-4-6",
        new_provider="anthropic",
        channel_visibility={},
    ).model_copy(update={"timestamp": timestamp})


def _write_cross_run_manifest(run_dir: Path, replaced_agent_id: str) -> None:
    """Mark ``run_dir`` as a cross-run replace-agent run."""
    manifest = CrossRunReplaceManifest(
        source_a_run_id="scenario/1",
        source_a_run_dir="runs/scenario/1",
        source_b_run_id="scenario/2",
        source_b_run_dir="runs/scenario/2",
        imported_history_source=IMPORTED_HISTORY_SOURCE_FILENAME,
        round_start=5,
        rounds_after_swap=3,
        target_event_id="evt-a",
        source_b_round_end=4,
        source_b_cutoff_event_id="evt-b",
        replaced_agent_id=replaced_agent_id,
        imported_model="claude-sonnet-4-6",
        imported_provider="anthropic",
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        replaced_at=1_780_000_000.0,
    )
    (run_dir / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_text(manifest.model_dump_json())


def _write_history_transfer_manifest(run_dir: Path, transferred_agent_id: str) -> None:
    """Mark ``run_dir`` as a history-transfer run seating ``transferred_agent_id``."""
    write_history_transfer_manifest(
        run_dir=run_dir,
        manifest=HistoryTransferManifest(
            source_run_id="other_scenario/1",
            source_run_dir="runs/other_scenario/1",
            source_round_end=4,
            seats=[
                TransferredSeat(
                    agent_id=transferred_agent_id,
                    source_agent_id="speaker",
                    source_model="claude-sonnet-4-6",
                    source_provider="anthropic",
                    history_file=f"transferred_history_{transferred_agent_id}.json",
                )
            ],
            transferred_at=1_780_000_000.0,
        ),
    )


def _write_replace_manifest(run_dir: Path, replaced_agent_id: str | None) -> None:
    """Mark ``run_dir`` as a replace-agent (or fork-at-round) run."""
    write_replace_manifest(
        run_dir=run_dir,
        round_start=5,
        rounds_after_swap=3,
        target_event_id="evt-a",
        replaced_agent_id=replaced_agent_id,
        channels_with_visible_history=[],
        blocked_tool_call_channels=[],
        channel_history_floors={},
        history_floor_round=None,
    )


def test_a_plain_source_is_accepted(tmp_path: Path) -> None:
    """A run with no derivation manifest has one continuous timeline."""
    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_a_cross_run_source_is_refused(tmp_path: Path) -> None:
    """The imported seat's history cannot be rebuilt past its import boundary."""
    _write_cross_run_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a cross-run replace-agent"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="observer")


def test_a_history_transfer_source_is_refused(tmp_path: Path) -> None:
    """A fork rebuilds from the log, which lacks the history the transferred seat started with."""
    _write_history_transfer_manifest(run_dir=tmp_path, transferred_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a history-transfer run"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_a_replace_agent_source_cannot_be_forked(tmp_path: Path) -> None:
    """A fork rebuilds the replaced seat pass-through, resurrecting the predecessor."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a replace-agent run.*'observer'"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_a_replace_agent_source_refuses_replacing_a_different_seat(tmp_path: Path) -> None:
    """The other seat would then rebuild pass-through with the predecessor's turns."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"is a replace-agent run"):
        refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="engineer")


def test_a_replace_agent_source_accepts_re_replacing_the_same_seat(tmp_path: Path) -> None:
    """The new replacement's filters cover that seat's whole prior history."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id="observer")


def test_a_fork_at_round_source_is_accepted(tmp_path: Path) -> None:
    """A fork-at-round run replaced no seat, so its log is one clean timeline."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id=None)

    refuse_unforkable_source(source_run_dir=tmp_path, replaced_agent_id=None)


def test_source_b_refuses_importing_its_own_replaced_seat(tmp_path: Path) -> None:
    """B's log holds the replaced-away agent's turns before B's own boundary."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"whose own boundary replaced 'observer'"):
        refuse_seat_with_mixed_history(source_run_dir=tmp_path, agent_id="observer")


def test_source_b_refuses_importing_a_seat_it_imported_itself(tmp_path: Path) -> None:
    """B's imported seat's real earlier context lives in B's own sidecar, never read here."""
    _write_cross_run_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    with pytest.raises(ValueError, match=r"whose own boundary replaced 'observer'"):
        refuse_seat_with_mixed_history(source_run_dir=tmp_path, agent_id="observer")


def test_source_b_accepts_importing_an_untouched_seat(tmp_path: Path) -> None:
    """A seat B never replaced has all of its own turns in B's log."""
    _write_replace_manifest(run_dir=tmp_path, replaced_agent_id="observer")

    refuse_seat_with_mixed_history(source_run_dir=tmp_path, agent_id="engineer")


def test_a_source_refuses_taking_a_seat_it_seated_with_a_transferred_history(
    tmp_path: Path,
) -> None:
    """The seat's earlier history lives in the transfer sidecar, not in the log."""
    _write_history_transfer_manifest(run_dir=tmp_path, transferred_agent_id="observer")

    with pytest.raises(ValueError, match=r"history-transfer run whose seat 'observer'"):
        refuse_seat_with_mixed_history(source_run_dir=tmp_path, agent_id="observer")


def test_a_history_transfer_source_accepts_a_seat_that_started_fresh(tmp_path: Path) -> None:
    """A seat the transfer left alone has all of its own turns in the log."""
    _write_history_transfer_manifest(run_dir=tmp_path, transferred_agent_id="observer")

    refuse_seat_with_mixed_history(source_run_dir=tmp_path, agent_id="engineer")


def test_a_boundary_behind_an_in_run_swap_is_refused() -> None:
    """The swapped seat would rebuild pass-through under the pre-swap model."""
    events: list[SimulationEvent] = [_swap(agent_id="observer", before_boundary=True)]

    with pytest.raises(ValueError, match=r"swapped seat 'observer' in-run at round 10"):
        refuse_boundary_with_swapped_seats(
            events=events,
            boundary_timestamp=_BOUNDARY,
            replaced_agent_id=None,
        )


def test_a_swapped_seat_can_be_replaced_again() -> None:
    """The new replacement's filters cover that seat's whole prior history."""
    events: list[SimulationEvent] = [_swap(agent_id="observer", before_boundary=True)]

    refuse_boundary_with_swapped_seats(
        events=events,
        boundary_timestamp=_BOUNDARY,
        replaced_agent_id="observer",
    )


def test_a_swap_past_the_boundary_does_not_refuse() -> None:
    """A later swap is truncated away with the rest of the source's timeline."""
    events: list[SimulationEvent] = [_swap(agent_id="observer", before_boundary=False)]

    refuse_boundary_with_swapped_seats(
        events=events,
        boundary_timestamp=_BOUNDARY,
        replaced_agent_id=None,
    )


def test_source_b_refuses_importing_a_seat_it_swapped_in_run() -> None:
    """B's log for that seat mixes the predecessor's and the swapped-in agent's turns."""
    events: list[SimulationEvent] = [_swap(agent_id="observer", before_boundary=True)]

    with pytest.raises(ValueError, match=r"the source run swapped seat 'observer'"):
        refuse_seat_swapped_before_cutoff(
            source_events=events,
            cutoff_timestamp=_BOUNDARY,
            agent_id="observer",
        )


def test_source_b_accepts_a_swap_of_a_different_seat() -> None:
    """A swap elsewhere leaves the imported seat's log clean."""
    events: list[SimulationEvent] = [_swap(agent_id="engineer", before_boundary=True)]

    refuse_seat_swapped_before_cutoff(
        source_events=events,
        cutoff_timestamp=_BOUNDARY,
        agent_id="observer",
    )
