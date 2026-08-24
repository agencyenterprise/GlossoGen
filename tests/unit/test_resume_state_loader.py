"""How a resumed run decides between re-opening its round and advancing past it.

``apply_fork_boundary`` compares the manifest's entry round against the clone's
last advanced round. Equal means the source advanced into the entry round and
the resume re-opens it, which is what every manifest recorded before final-round
forks existed also does. One behind means the boundary round was the source's
last: the resume must advance, and the entry round's message-count snapshot must
exist or windowed channel visibility would silently fall back to full history.
"""

from datetime import UTC, datetime
from pathlib import Path

import orjson
import pytest

from glossogen.cross_run_replace_manifest import (
    CROSS_RUN_REPLACE_MANIFEST_FILENAME,
    CrossRunReplaceManifest,
)
from glossogen.message_rewind import RewindState
from glossogen.models.event import MessageSent, RoundAdvanced, SimulationEvent
from glossogen.models.message import SimulationMessage
from glossogen.replace_manifest import REPLACE_MANIFEST_FILENAME, ReplaceManifest
from glossogen.resume_state_loader import (
    apply_fork_boundary,
    load_resume_state,
    read_replace_manifest_info,
)
from glossogen.runtime.scheduled_events import ChannelVisibilityFromRound, ChannelVisibilityFull


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
        messages_by_channel={"link": [_message("m-1"), _message("m-2")], "side": []},
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
    manifest = ReplaceManifest(
        source_run_id="smoke/1",
        source_run_dir="/runs/smoke/1",
        round_start=3,
        rounds_after_swap=2,
        target_event_id="e-9",
        replaced_agent_id=replaced_agent_id,
        replacement_model=None,
        replacement_provider=None,
        channels_with_visible_history=["link", "side"],
        blocked_tool_call_channels=["postmortem"],
        channel_history_floors={"side": 2},
        replaced_at=1_700_000_000.0,
    )
    (run_dir / REPLACE_MANIFEST_FILENAME).write_bytes(orjson.dumps(manifest.model_dump()))


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
        MessageSent(round_number=3, message=_message("m-post-boundary"), token_count=4),
    ]

    with pytest.raises(ValueError, match=r"already played past its boundary"):
        await load_resume_state(run_dir=tmp_path, events=events)
