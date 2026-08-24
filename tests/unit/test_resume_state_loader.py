"""How a resumed run decides between re-opening its round and advancing past it.

``apply_fork_boundary`` compares the manifest's entry round against the clone's
last advanced round. At or past the entry round means the log already opened it
and the resume re-opens it, which is what every manifest recorded before
final-round forks existed also does. One behind means the boundary round was
the source's last: the resume must advance, and the entry round's message-count
snapshot must exist or windowed channel visibility would silently fall back to
full history.

Crash recovery hangs on ``classify_fork_progress``: agent re-registrations past
the anchor are a launch, clock lifecycle events are progress recovery must keep
(re-anchoring would log them twice), and anything else is play.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import orjson
import pytest

from glossogen.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.message_rewind import RewindState
from glossogen.models.event import (
    AgentRegistered,
    InjectionDelivered,
    MessageSent,
    RoundAdvanced,
    RoundEnded,
    RoundResultRecorded,
    SimulationEvent,
    SimulationStarted,
    ToolCallInvoked,
)
from glossogen.models.event_base import EventBase
from glossogen.models.message import SimulationMessage
from glossogen.resume_state_loader import (
    ForkProgress,
    apply_fork_boundary,
    classify_fork_progress,
    load_resume_state,
    read_replace_manifest_info,
)
from glossogen.runtime.scheduled_events import ChannelVisibilityFromRound, ChannelVisibilityFull
from tests.fakes.replace_manifests import write_replace_manifest


class _ScenarioCaseOpened(EventBase):
    """Stands in for a scenario's own event type, unknown to the loader."""

    event_type: Literal["scenario_case_opened"] = "scenario_case_opened"


def _message(message_id: str) -> SimulationMessage:
    """A minimal channel message; only the count per channel matters here."""
    return SimulationMessage(
        message_id=message_id,
        channel_id="link",
        sender_agent_id="first_agent",
        sender_display_name="First Agent",
        text="AB12",
        timestamp=datetime(2026, 8, 1, tzinfo=UTC),
        round_number=1,
    )


def _state(round_number: int) -> RewindState:
    """A rewind state whose clone last advanced into ``round_number``."""
    return RewindState(
        round_number=round_number,
        messages_by_channel={
            "link": [_message(message_id="m-1"), _message(message_id="m-2")],
            "side": [],
        },
        injected_rounds={},
        scenario_name="smoke",
        scenario_config={"round_count": 3},
        agent_registrations=[],
        agent_message_histories={},
        replaced_agent_ids=frozenset(),
        replaced_agent_channel_visibility={},
        channel_message_count_at_round_start={2: {"link": 1}},
        rounds_with_fired_scheduler_events=frozenset(),
        enter_round_by_advancing=False,
        simulation_start_time=datetime(2026, 8, 1, tzinfo=UTC),
    )


def test_a_clone_that_advanced_into_the_entry_round_re_opens_it() -> None:
    """The shape every manifest recorded before final-round forks produces."""
    state = apply_fork_boundary(state=_state(round_number=3), entry_round=3)

    assert state.enter_round_by_advancing is False
    assert state.channel_message_count_at_round_start == {2: {"link": 1}}


def test_a_clone_ending_at_the_boundary_round_advances_with_a_synthesized_snapshot() -> None:
    """Without the snapshot, a from-round window at the entry round would mean full history."""
    state = apply_fork_boundary(state=_state(round_number=2), entry_round=3)

    assert state.enter_round_by_advancing is True
    assert state.channel_message_count_at_round_start[3] == {"link": 2, "side": 0}
    assert state.channel_message_count_at_round_start[2] == {"link": 1}


def test_a_clone_more_than_one_round_behind_its_manifest_is_refused() -> None:
    """Anything else means the clone was truncated somewhere its manifest does not describe."""
    with pytest.raises(ValueError, match=r"clone is inconsistent with its manifest"):
        apply_fork_boundary(state=_state(round_number=1), entry_round=3)


def _write_manifest(run_dir: Path, replaced_agent_id: str | None) -> None:
    """Write a replace manifest with entry round 3 and one windowed channel."""
    write_replace_manifest(
        run_dir=run_dir,
        round_start=3,
        rounds_after_swap=2,
        target_event_id="e-9",
        replaced_agent_id=replaced_agent_id,
        channels_with_visible_history=["link", "side"],
        blocked_tool_call_channels=["postmortem"],
        channel_history_floors={"side": 2},
    )


def test_the_manifest_projection_names_the_entry_round_and_visibility(tmp_path: Path) -> None:
    """The on-disk ``round_start`` field is the round the fork enters."""
    _write_manifest(run_dir=tmp_path, replaced_agent_id="first_agent")

    info = read_replace_manifest_info(run_dir=tmp_path)

    assert info is not None
    assert info.entry_round == 3
    assert info.replaced_agent_id == "first_agent"
    assert info.channel_visibility["link"] == ChannelVisibilityFull()
    assert info.channel_visibility["side"] == ChannelVisibilityFromRound(round_floor=2)
    assert info.channel_visibility["postmortem"].kind == "none"


def test_a_directory_without_a_manifest_projects_to_none(tmp_path: Path) -> None:
    """A plain interrupted run resumes with no manifest at all."""
    assert read_replace_manifest_info(run_dir=tmp_path) is None


async def test_a_progressed_cross_run_fork_refuses_crash_recovery(tmp_path: Path) -> None:
    """The imported agent's post-boundary turns cannot be re-seeded from source B.

    Recovering from the manifest's anchor would silently discard the fork's
    progress, so a cross-run fork whose log grew past its anchor is refused
    with the fix spelled out.
    """
    manifest = CrossRunReplaceManifest(
        source_a_run_id="smoke/1",
        source_a_run_dir="/runs/smoke/1",
        source_b_run_id="smoke/2",
        source_b_run_dir="/runs/smoke/2",
        imported_history_source="imported_history_source.jsonl",
        round_start=3,
        rounds_after_swap=0,
        target_event_id="e-anchor",
        source_b_round_end=2,
        source_b_cutoff_event_id="",
        replaced_agent_id="first_agent",
        imported_model="scripted",
        imported_provider="anthropic",
        channels_with_visible_history=["link"],
        blocked_tool_call_channels=[],
        replaced_at=1_700_000_000.0,
    )
    (tmp_path / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_bytes(
        orjson.dumps(manifest.model_dump())
    )
    events: list[SimulationEvent] = [
        RoundAdvanced(event_id="e-anchor", round_number=3, trigger="all_agents_idle"),
        MessageSent(round_number=3, message=_message(message_id="m-post-boundary"), token_count=4),
    ]

    with pytest.raises(ValueError, match=r"already played past its boundary"):
        await load_resume_state(run_dir=tmp_path, events=events)


def _stamped(events: list[SimulationEvent]) -> list[SimulationEvent]:
    """Give each event a distinct increasing timestamp, in list order."""
    start = datetime(2026, 8, 1, tzinfo=UTC)
    stamped: list[SimulationEvent] = []
    for index, event in enumerate(events):
        base = event
        assert isinstance(base, EventBase)
        stamped.append(base.model_copy(update={"timestamp": start + timedelta(seconds=index)}))
    return stamped


def _started() -> SimulationStarted:
    """A minimal SimulationStarted so history reconstruction can anchor elapsed time."""
    return SimulationStarted(
        round_number=0,
        run_id="smoke/1",
        scenario_name="smoke",
        scenario_description="",
        channel_ids=["link"],
        scenario_config={"round_count": 3},
        provider="anthropic",
    )


def _registered(agent_id: str) -> AgentRegistered:
    """A minimal registration for ``agent_id``."""
    return AgentRegistered(
        round_number=0,
        agent_id=agent_id,
        role_name="First Agent",
        system_prompt="do things",
        channel_ids=["link"],
        tool_names=["send_message"],
        model="scripted",
        provider="anthropic",
        max_tokens=1024,
    )


async def test_a_fork_that_crashed_after_its_fresh_advance_does_not_advance_again(
    tmp_path: Path,
) -> None:
    """The clock logs the entry round's advance before any agent acts.

    A crash in that window leaves ``RoundAdvanced(entry, "fork_after_round")``
    in the log; recovery must anchor at the log's end and re-open that round,
    or the resumed clock would append a second advance.
    """
    _write_manifest(run_dir=tmp_path, replaced_agent_id=None)
    events = _stamped(
        events=[
            _started(),
            _registered(agent_id="first_agent"),
            RoundAdvanced(round_number=1, trigger="simulation_start"),
            RoundAdvanced(round_number=2, trigger="all_agents_idle"),
            RoundEnded(event_id="e-9", round_number=2, trigger="all_agents_idle"),
            _registered(agent_id="first_agent"),
            RoundAdvanced(round_number=3, trigger="fork_after_round"),
            InjectionDelivered(round_number=3, agent_id="first_agent", text="round 3 briefing"),
        ]
    )

    state = await load_resume_state(run_dir=tmp_path, events=events)

    assert state.enter_round_by_advancing is False
    assert state.round_number == 3
    assert state.injected_rounds["first_agent"] == 3


async def test_a_fork_that_played_a_messageless_round_keeps_its_verdict(
    tmp_path: Path,
) -> None:
    """A round can end with zero channel messages (idle or refusing agents).

    Its verdict and the advance past it are already in the log, so recovery
    must not re-anchor at the boundary and replay the judged round.
    """
    _write_manifest(run_dir=tmp_path, replaced_agent_id=None)
    events = _stamped(
        events=[
            _started(),
            _registered(agent_id="first_agent"),
            RoundAdvanced(round_number=1, trigger="simulation_start"),
            RoundAdvanced(round_number=2, trigger="all_agents_idle"),
            RoundAdvanced(event_id="e-9", round_number=3, trigger="all_agents_idle"),
            InjectionDelivered(round_number=3, agent_id="first_agent", text="round 3 briefing"),
            RoundEnded(round_number=3, trigger="round_timeout"),
            RoundResultRecorded(round_number=3, success=False, team_id=None, reason="timeout"),
            RoundAdvanced(round_number=4, trigger="round_timeout"),
        ]
    )

    state = await load_resume_state(run_dir=tmp_path, events=events)

    assert state.enter_round_by_advancing is False
    assert state.round_number == 4


async def test_a_cross_run_fork_that_crashed_after_clock_bookkeeping_recovers(
    tmp_path: Path,
) -> None:
    """Only actual play is unrecoverable for a cross-run fork.

    A crash after the clock delivered injections, but before any agent acted,
    leaves nothing the imported agent's history would need re-seeding for, so
    recovery proceeds at the log's end instead of refusing.
    """
    imported_events = _stamped(
        events=[
            _started(),
            _registered(agent_id="first_agent"),
        ]
    )
    imported_path = tmp_path / "imported_history_source.jsonl"
    imported_path.write_text("\n".join(event.model_dump_json() for event in imported_events) + "\n")
    manifest = CrossRunReplaceManifest(
        source_a_run_id="smoke/1",
        source_a_run_dir="/runs/smoke/1",
        source_b_run_id="smoke/2",
        source_b_run_dir="/runs/smoke/2",
        imported_history_source="imported_history_source.jsonl",
        round_start=3,
        rounds_after_swap=0,
        target_event_id="e-anchor",
        source_b_round_end=2,
        source_b_cutoff_event_id="",
        replaced_agent_id="first_agent",
        imported_model="scripted",
        imported_provider="anthropic",
        channels_with_visible_history=["link"],
        blocked_tool_call_channels=[],
        replaced_at=1_700_000_000.0,
    )
    (tmp_path / CROSS_RUN_REPLACE_MANIFEST_FILENAME).write_bytes(
        orjson.dumps(manifest.model_dump())
    )
    events = _stamped(
        events=[
            _started(),
            _registered(agent_id="first_agent"),
            RoundAdvanced(round_number=1, trigger="simulation_start"),
            RoundAdvanced(round_number=2, trigger="all_agents_idle"),
            RoundAdvanced(event_id="e-anchor", round_number=3, trigger="all_agents_idle"),
            _registered(agent_id="first_agent"),
            _ScenarioCaseOpened(round_number=3),
            InjectionDelivered(round_number=3, agent_id="first_agent", text="round 3 briefing"),
        ]
    )

    state = await load_resume_state(run_dir=tmp_path, events=events)

    assert state.enter_round_by_advancing is False
    assert state.round_number == 3
    assert state.replaced_agent_ids == frozenset({"first_agent"})
    assert state.injected_rounds["first_agent"] == 3


def test_a_scenarios_own_round_open_events_are_progress_not_play() -> None:
    """Most scenarios log case events from ``on_round_advanced`` before agents run.

    Those land past the anchor on every launch, so counting them as play would
    refuse cross-run recovery in its main use case. Play is only what the
    agents themselves produce.
    """
    events = _stamped(
        events=[
            RoundAdvanced(event_id="e-anchor", round_number=3, trigger="all_agents_idle"),
            _registered(agent_id="first_agent"),
            _ScenarioCaseOpened(round_number=3),
            InjectionDelivered(round_number=3, agent_id="first_agent", text="round 3 briefing"),
        ]
    )

    progress = classify_fork_progress(events=events, target_event_id="e-anchor")

    assert progress is ForkProgress.ADVANCED


def test_an_agents_tool_call_past_the_anchor_is_play() -> None:
    """A tool call reaches the reconstructed history, so it cannot be re-anchored over."""
    events = _stamped(
        events=[
            RoundAdvanced(event_id="e-anchor", round_number=3, trigger="all_agents_idle"),
            _ScenarioCaseOpened(round_number=3),
            ToolCallInvoked(
                round_number=3,
                agent_id="first_agent",
                call_id="c-1",
                tool_name="read_notifications",
                arguments={},
            ),
        ]
    )

    progress = classify_fork_progress(events=events, target_event_id="e-anchor")

    assert progress is ForkProgress.PLAYED


async def test_recovery_re_anchors_hidden_channels_at_the_boundary(tmp_path: Path) -> None:
    """A blocked channel's join index must not move to the crash point.

    ``ChannelVisibilityNone`` resolves to a join index of every message so
    far; recovery anchors the state walk at the log's end, so keeping ``None``
    would hide the post-boundary messages the replacement had already seen.
    The pristine launch keeps ``None``, whose resolution at the boundary is
    the same count.
    """
    _write_manifest(run_dir=tmp_path, replaced_agent_id="first_agent")
    base: list[SimulationEvent] = [
        _started(),
        _registered(agent_id="first_agent"),
        RoundAdvanced(round_number=1, trigger="simulation_start"),
        RoundAdvanced(round_number=2, trigger="all_agents_idle"),
        RoundAdvanced(event_id="e-9", round_number=3, trigger="all_agents_idle"),
    ]

    pristine = await load_resume_state(run_dir=tmp_path, events=_stamped(events=base))
    pristine_visibility = pristine.replaced_agent_channel_visibility["first_agent"]
    assert pristine_visibility["postmortem"].kind == "none"

    played_events = _stamped(
        events=base
        + [
            MessageSent(
                round_number=3,
                message=_message(message_id="m-own-postmortem"),
                token_count=4,
            ),
        ]
    )

    recovered = await load_resume_state(run_dir=tmp_path, events=played_events)

    visibility = recovered.replaced_agent_channel_visibility["first_agent"]
    assert visibility["postmortem"] == ChannelVisibilityFromRound(round_floor=3)
    assert visibility["link"] == ChannelVisibilityFull()
    assert visibility["side"] == ChannelVisibilityFromRound(round_floor=2)
