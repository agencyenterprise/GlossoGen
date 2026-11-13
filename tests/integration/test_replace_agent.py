"""Replacing one seat of a finished run at a round boundary, end to end.

Replace-agent is a fork-at-round in which one seat restarts under a new model.
The seat is seeded with its predecessor's tool calls only. A channel keeps its
whole past, or with a floor only the rounds from the floor on; only the
channels the scenario blocks are hidden. ``history_floor_round`` windows the
predecessor's other tool calls by round.

When the fork crashes after the replacement has played and is resumed, the log
also holds the replacement's own turns. The same seeding filters run over all
of it, bounded by ``filter_below_round`` to the rounds before the entry round,
and the live channel view stays anchored at the manifest's window rather than
at the crash point.

A seat that sees more than it was meant to fails silently: the run plays, and
the experiment measures a newcomer that was never new. A recovered seat that
loses its own turns plays on with amnesia, just as silently. So the
assertions are about what the replaced seat is handed, in its seeded history
and in what ``read_channel`` returns to it after the resume.
"""

from pathlib import Path
from typing import Any

import orjson
import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart

from glossogen.models.event import MessageSent, RoundAdvanced, SimulationEnded, ToolResultReceived
from glossogen.run_derivation.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.run_derivation.run_launching import PreparedForkRun
from glossogen.run_replay.message_rewind import RewindState
from glossogen.run_replay.resume_state_loader import load_resume_state
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.testing.scripted_agent import PacedTurn, RoundGate, SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    resume_simulation,
    run_round_paced_simulation,
)
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    RECORD_TOOL_NAME,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

SOURCE_ROUND_COUNT = 3
ENTRY_ROUND = 3
REPLACED_SEAT = FIRST_AGENT_ID
REPLACEMENT_MODEL = "claude-haiku-4-5-20251001"
REPLACEMENT_SAID = "replacement-said-r3"
REPLACEMENT_THOUGHT = "replacement-thought-r3"


def source_round(*, agent_id: str, round_number: int) -> list[PacedTurn]:
    """One source round: record a finding, speak on #link, then park.

    The turns sit behind a ``RoundGate``, so the round each call lands in is the
    script's statement rather than the scheduler's choice. The finding, the
    message and the thought all name the agent and the round, so a test can tell
    which of the predecessor's rounds survived the filters.
    """
    return [
        RoundGate(round_number=round_number),
        ToolTurn(
            tool_name=RECORD_TOOL_NAME,
            args={"finding": f"{agent_id}-finding-r{round_number}"},
        ),
        ToolTurn(
            tool_name="send_message",
            args={
                "channel_id": LINK_CHANNEL_ID,
                "text": f"{agent_id}-said-r{round_number}",
                "force": True,
            },
        ),
        SayTurn(text=f"{agent_id}-thought-r{round_number}"),
    ]


def idle_script() -> list[ScriptedTurn]:
    """Park at once."""
    return [ToolTurn(tool_name="read_notifications", args={}), SayTurn(text="idle")]


def read_link() -> ToolTurn:
    """Read the whole of #link."""
    return ToolTurn(tool_name="read_channel", args={"channel_id": LINK_CHANNEL_ID, "last_n": 50})


def replacement_first_round() -> list[ScriptedTurn]:
    """What the replacement does in the fork's first round, before the crash."""
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": REPLACEMENT_SAID, "force": True},
        ),
        read_link(),
        SayTurn(text=REPLACEMENT_THOUGHT),
    ]


async def make_source_run(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run a three-round source to completion and return its run directory."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    scripts = {
        agent_id: [
            turn
            for round_number in range(1, SOURCE_ROUND_COUNT + 1)
            for turn in source_round(agent_id=agent_id, round_number=round_number)
        ]
        for agent_id in (FIRST_AGENT_ID, SECOND_AGENT_ID)
    }
    result = await run_round_paced_simulation(
        scenario=SmokeScenario(
            knobs=SmokeKnobs(
                round_count=SOURCE_ROUND_COUNT,
                max_round_duration_seconds=45,
                model_overrides={},
            )
        ),
        scripts=scripts,
        tmp_path=source_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    assert result.of_type(event_type=SimulationEnded), "source run did not finish"
    sent_rounds = {
        str(m.text): int(m.round_number) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)
    }
    assert sent_rounds[f"{SECOND_AGENT_ID}-said-r1"] == 1
    assert sent_rounds[f"{SECOND_AGENT_ID}-said-r2"] == 2
    return source_dir


async def replace_the_first_seat(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rounds_after: int | None,
    channels_with_visible_history: list[str],
    channel_history_floors: dict[str, int],
    history_floor_round: int | None,
) -> PreparedForkRun:
    """Run the source, then replace the first seat after round 2 without launching.

    The smoke scenario is registered nowhere, so the registry lookup is pointed
    at it directly, and the credential preflight gets a stub anthropic key.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.run_derivation.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return await prepare_replace_agent_run(
        request=ReplaceAgentRequest(
            source_run_dir=source_dir,
            scenario_name="smoke",
            after_round=ENTRY_ROUND - 1,
            rounds_after=rounds_after,
            replaced_agent_id=REPLACED_SEAT,
            model=REPLACEMENT_MODEL,
            provider="anthropic",
            knobs=None,
            channels_with_visible_history=channels_with_visible_history,
            channel_history_floors=channel_history_floors,
            history_floor_round=history_floor_round,
            runs_dir=tmp_path / "runs",
        )
    )


async def resume_state_of(*, prepared: PreparedForkRun) -> RewindState:
    """The rewind state the next resume of ``prepared`` starts from."""
    events = await load_events(
        log_path=event_log_path(run_dir=prepared.new_run_dir, scenario_name="smoke")
    )
    return await load_resume_state(run_dir=prepared.new_run_dir, events=events)


async def seeded_responses(*, prepared: PreparedForkRun, agent_id: str) -> list[ModelResponse]:
    """The model responses ``agent_id`` is seeded with when ``prepared`` resumes."""
    state = await resume_state_of(prepared=prepared)
    return [
        message
        for message in state.agent_message_histories.get(agent_id, [])
        if isinstance(message, ModelResponse)
    ]


def tool_calls(responses: list[ModelResponse]) -> list[str]:
    """Each kept tool call as ``name:args``, in history order."""
    return [
        f"{part.tool_name}:{orjson.dumps(part.args_as_dict()).decode()}"
        for response in responses
        for part in response.parts
        if isinstance(part, ToolCallPart)
    ]


def texts(responses: list[ModelResponse]) -> list[str]:
    """Every text part in the responses."""
    return [
        part.content
        for response in responses
        for part in response.parts
        if isinstance(part, TextPart)
    ]


async def resume_fork(
    *,
    prepared: PreparedForkRun,
    monkeypatch: pytest.MonkeyPatch,
    replaced_seat_script: list[ScriptedTurn],
) -> SimulationResult:
    """Resume the fork in-process, with the knobs its launch would pass as ``--config``."""
    config: dict[str, Any] = orjson.loads(
        (prepared.new_run_dir / "replace_config.json").read_bytes()
    )
    return await resume_simulation(
        scenario=SmokeScenario(knobs=SmokeKnobs.model_validate(config)),
        scripts={REPLACED_SEAT: replaced_seat_script, SECOND_AGENT_ID: idle_script()},
        run_dir=prepared.new_run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def link_reads_by_the_replaced_seat(*, result: SimulationResult, round_number: int) -> list[str]:
    """What each ``read_channel`` by the replaced seat in ``round_number`` returned."""
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == REPLACED_SEAT
        and event.tool_name == "read_channel"
        and event.round_number == round_number
    ]


async def first_read_after_replacing(
    *, prepared: PreparedForkRun, monkeypatch: pytest.MonkeyPatch
) -> str:
    """Resume the fork with the replaced seat reading #link once; return what it read."""
    result = await resume_fork(
        prepared=prepared,
        monkeypatch=monkeypatch,
        replaced_seat_script=[read_link(), *idle_script()],
    )
    reads = link_reads_by_the_replaced_seat(result=result, round_number=ENTRY_ROUND)
    assert len(reads) == 1, f"expected one read_channel by the replaced seat, got {reads}"
    return reads[0]


def crash_at_the_advance_into(*, log_path: Path, round_number: int) -> None:
    """Cut the log just after ``RoundAdvanced(round_number)``, as a crash there would.

    Everything the fork logged later, its end marker included, is gone, so the
    next resume takes the recovery path for a fork that already played.
    """
    kept: list[bytes] = []
    for line in log_path.read_bytes().splitlines():
        if not line.strip():
            continue
        kept.append(line)
        event = orjson.loads(line)
        if event["event_type"] == "round_advanced" and event["round_number"] == round_number:
            break
    else:
        raise AssertionError(f"the fork never advanced into round {round_number}")
    log_path.write_bytes(b"\n".join(kept) + b"\n")


async def played_then_crashed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> PreparedForkRun:
    """A two-round fork, #link windowed from round 2, that crashed as round 4 opened.

    The replacement sent on #link, read it and spoke in round 3 first.
    """
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=2,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={LINK_CHANNEL_ID: 2},
        history_floor_round=None,
    )
    first_launch = await resume_fork(
        prepared=prepared,
        monkeypatch=monkeypatch,
        replaced_seat_script=replacement_first_round(),
    )
    sent_in = {
        str(event.message.text): int(event.round_number)
        for event in first_launch.of_type(event_type=MessageSent)
    }
    assert sent_in[REPLACEMENT_SAID] == ENTRY_ROUND, "the replacement must play in round 3"
    crash_at_the_advance_into(log_path=first_launch.log_path, round_number=ENTRY_ROUND + 1)
    return prepared


async def test_the_replaced_seat_is_seeded_with_tool_calls_and_no_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The predecessor's words and thoughts are gone; the other seat keeps its own."""
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={},
        history_floor_round=None,
    )

    replaced = await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT)
    calls = tool_calls(responses=replaced)
    assert texts(responses=replaced) == []
    assert any(f"{REPLACED_SEAT}-finding-r1" in call for call in calls)
    assert any(f"{REPLACED_SEAT}-said-r2" in call for call in calls)
    assert not any("-r3" in call for call in calls), "round 3 is past the boundary"

    untouched = await seeded_responses(prepared=prepared, agent_id=SECOND_AGENT_ID)
    assert f"{SECOND_AGENT_ID}-thought-r2" in texts(responses=untouched)


async def test_the_seat_floor_alone_leaves_channel_sends_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a channel floor, ``history_floor_round`` windows only the other tools.

    A seat that belongs to no channel depends on this path: the seat floor is
    the only thing that drops its earlier calls.
    """
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={},
        history_floor_round=2,
    )

    calls = tool_calls(responses=await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT))
    assert not any(f"{REPLACED_SEAT}-finding-r1" in call for call in calls)
    assert any(f"{REPLACED_SEAT}-finding-r2" in call for call in calls)
    assert any(f"{REPLACED_SEAT}-said-r1" in call for call in calls)


async def test_a_floor_of_the_entry_round_seeds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``after_round + 1`` is the documented way to give the seat no prior history."""
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={LINK_CHANNEL_ID: ENTRY_ROUND},
        history_floor_round=ENTRY_ROUND,
    )

    replaced = await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT)

    assert tool_calls(responses=replaced) == []


async def test_a_visible_channel_shows_the_replaced_seat_its_whole_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={},
        history_floor_round=None,
    )

    read = await first_read_after_replacing(prepared=prepared, monkeypatch=monkeypatch)

    assert f"{SECOND_AGENT_ID}-said-r1" in read
    assert f"{SECOND_AGENT_ID}-said-r2" in read


async def test_a_windowed_channel_shows_the_replaced_seat_only_rounds_from_the_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[LINK_CHANNEL_ID],
        channel_history_floors={LINK_CHANNEL_ID: 2},
        history_floor_round=2,
    )

    read = await first_read_after_replacing(prepared=prepared, monkeypatch=monkeypatch)

    assert f"{SECOND_AGENT_ID}-said-r1" not in read
    assert f"{SECOND_AGENT_ID}-said-r2" in read


async def test_a_channel_left_out_of_the_visible_list_keeps_its_past(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Leaving a channel out of the list does not hide it.

    Only the scenario's blocked channels are hidden on replace-agent. A channel
    that is neither listed nor blocked keeps its join index, so ``read_channel``
    returns its whole past, and the predecessor's sends on it stay in the seat's
    seeded history.
    """
    prepared = await replace_the_first_seat(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        rounds_after=None,
        channels_with_visible_history=[],
        channel_history_floors={},
        history_floor_round=None,
    )

    calls = tool_calls(responses=await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT))
    assert any(f"{REPLACED_SEAT}-said-r1" in call for call in calls)

    read = await first_read_after_replacing(prepared=prepared, monkeypatch=monkeypatch)
    assert f"{SECOND_AGENT_ID}-said-r1" in read
    assert f"{SECOND_AGENT_ID}-said-r2" in read


async def test_recovery_reopens_the_round_the_crash_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The state walks to the crash, not back to the fork boundary.

    Re-anchoring at the boundary would replay round 3 on top of the round the
    replacement already played. The window's snapshot for round 2 survives the
    longer walk, so the live view can still resolve it.
    """
    prepared = await played_then_crashed(tmp_path=tmp_path, monkeypatch=monkeypatch)

    state = await resume_state_of(prepared=prepared)

    assert state.round_number == ENTRY_ROUND + 1
    assert state.enter_round_by_advancing is False
    assert state.replaced_agent_ids == frozenset({REPLACED_SEAT})
    link_texts = [str(m.text) for m in state.messages_by_channel[LINK_CHANNEL_ID]]
    assert REPLACEMENT_SAID in link_texts
    assert 2 in state.channel_message_count_at_round_start


async def test_the_recovered_replacement_keeps_its_own_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its text, its send and its read of the windowed channel all survive.

    A windowed channel drops every ``read_channel`` and every text part when the
    seeding filters apply. They must apply only below the entry round.
    """
    prepared = await played_then_crashed(tmp_path=tmp_path, monkeypatch=monkeypatch)

    replaced = await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT)

    assert REPLACEMENT_THOUGHT in texts(responses=replaced)
    calls = tool_calls(responses=replaced)
    assert any(REPLACEMENT_SAID in call for call in calls)
    assert any(call.startswith("read_channel:") for call in calls)


async def test_the_recovered_replacement_still_sees_its_predecessor_filtered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No predecessor text, and nothing from below the #link window.

    The window's floor also floors the predecessor's other tools, so its
    round-1 finding goes with its round-1 message.
    """
    prepared = await played_then_crashed(tmp_path=tmp_path, monkeypatch=monkeypatch)

    replaced = await seeded_responses(prepared=prepared, agent_id=REPLACED_SEAT)

    assert not any(
        text.startswith(f"{REPLACED_SEAT}-thought") for text in texts(responses=replaced)
    )
    calls = tool_calls(responses=replaced)
    assert not any("-r1" in call for call in calls)
    assert any(f"{REPLACED_SEAT}-finding-r2" in call for call in calls)
    assert any(f"{REPLACED_SEAT}-said-r2" in call for call in calls)


async def test_the_recovered_replacement_reads_the_channel_from_the_window_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After recovery, ``read_channel`` shows round 2 onward, its own message included.

    The window resolves from the message count snapshotted when the source
    advanced into round 2. A recovered view that dropped the window would show
    round 1; one that lost the round-2 snapshot could not resolve it.
    """
    prepared = await played_then_crashed(tmp_path=tmp_path, monkeypatch=monkeypatch)

    resumed = await resume_fork(
        prepared=prepared,
        monkeypatch=monkeypatch,
        replaced_seat_script=[read_link(), *idle_script()],
    )

    reads = link_reads_by_the_replaced_seat(result=resumed, round_number=ENTRY_ROUND + 1)
    assert len(reads) == 1, f"expected one read in round 4, got {len(reads)}"
    read = reads[0]
    assert f"{SECOND_AGENT_ID}-said-r2" in read
    assert f"{REPLACED_SEAT}-said-r2" in read
    assert REPLACEMENT_SAID in read
    assert "-said-r1" not in read
    advances = [int(e.round_number) for e in resumed.of_type(event_type=RoundAdvanced)]
    assert advances.count(ENTRY_ROUND + 1) == 1, "recovery must not advance into round 4 twice"
