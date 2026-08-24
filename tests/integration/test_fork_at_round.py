"""Forking a finished run at a round boundary, end to end.

A fork after round N keeps rounds 1..N complete and plays N+1 onward in a new
run directory. Two shapes exist. When the source itself advanced past the
boundary, the clone ends at the source's ``RoundAdvanced(N+1)`` and the resume
re-opens that round. When round N was the source's final round, no such event
exists: the clone ends just before ``SimulationEnded`` and the resumed clock
must advance into a round the source never played.

The failure modes are silent. A fork that re-runs the boundary round doubles its
verdict; one that skips injection delivery plays a round no agent was briefed
for; a duplicated ``RoundAdvanced`` shifts every per-round metric. So the
assertions are about the merged event log's structure, not about whether the
resume ran.
"""

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import orjson
import pytest

from glossogen.evaluation.log_reader import load_events
from glossogen.models.event import AgentRegistered, RoundAdvanced, RunStatus, SimulationEnded
from glossogen.replace_agent import ReplaceAgentRequest, prepare_replace_agent_run
from glossogen.resume_state_loader import load_resume_state
from glossogen.run_launching import PreparedForkRun
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    resume_simulation,
    run_simulation,
)
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

SOURCE_ROUND_COUNT = 2


def speak_then_idle(*, text: str) -> list[ScriptedTurn]:
    """One send, then park. The suffix identifies the message, nothing more."""
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


def build_scenario(*, round_count: int) -> SmokeScenario:
    """Build the smoke scenario for ``round_count`` rounds."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=round_count,
            max_round_duration_seconds=45,
            model_overrides={},
        )
    )


async def make_source_run(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Run a two-round source to completion and return its run directory."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    result = await run_simulation(
        scenario=build_scenario(round_count=SOURCE_ROUND_COUNT),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="src-first") * SOURCE_ROUND_COUNT,
            SECOND_AGENT_ID: speak_then_idle(text="src-second") * SOURCE_ROUND_COUNT,
        },
        tmp_path=source_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    assert result.of_type(event_type="simulation_ended"), "source run did not finish"
    return source_dir


async def prepare_fork(
    *,
    source_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_round: int,
    rounds_after: int | None,
) -> PreparedForkRun:
    """Prepare a fork of the smoke source on disk, without launching anything.

    The smoke scenario is registered nowhere, so the registry lookup inside
    the prepare flow is pointed at it directly. The credential preflight
    reads the environment, so the anthropic key the source agents were
    registered under is stubbed.
    """

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr("glossogen.replace_agent.get_scenario_class", smoke_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return await prepare_replace_agent_run(
        request=ReplaceAgentRequest(
            source_run_dir=source_dir,
            scenario_name="smoke",
            after_round=after_round,
            rounds_after=rounds_after,
            replaced_agent_id=None,
            model=None,
            provider=None,
            knobs=None,
            channels_with_visible_history=None,
            channel_history_floors={},
            runs_dir=tmp_path / "runs",
        )
    )


async def resume_fork(
    *,
    prepared: PreparedForkRun,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Resume the prepared fork in-process, building the scenario from its config.

    ``replace_config.json`` is what the launched subprocess would pass as
    ``--config``, so building the knobs from it keeps the test on the same
    path a real fork takes.
    """
    config: dict[str, Any] = orjson.loads(
        (prepared.new_run_dir / "replace_config.json").read_bytes()
    )
    scenario = SmokeScenario(knobs=SmokeKnobs.model_validate(config))
    return await resume_simulation(
        scenario=scenario,
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="fork-first"),
            SECOND_AGENT_ID: speak_then_idle(text="fork-second"),
        },
        run_dir=prepared.new_run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def rounds_advanced(result: SimulationResult) -> list[tuple[int, str]]:
    """Every RoundAdvanced as (round_number, trigger), in log order."""
    return [
        (int(event["round_number"]), str(event["trigger"]))
        for event in result.of_type(event_type="round_advanced")
    ]


def first_index(result: SimulationResult, *, event_type: str, round_number: int) -> int:
    """Position of the first matching event in the merged log."""
    return next(
        index
        for index, event in enumerate(result.events)
        if event.get("event_type") == event_type and event.get("round_number") == round_number
    )


async def test_a_fork_before_the_source_end_re_opens_the_entry_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After round 1 of a two-round source, the fork replays round 2 and only round 2.

    The clone keeps the source's ``RoundAdvanced(2)``, so no fresh advance is
    logged, and the round-2 injections the truncation dropped are delivered
    again into the resumed sessions.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_fork(
        source_dir=source_dir,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        rounds_after=None,
    )

    manifest = orjson.loads((prepared.new_run_dir / "replace_manifest.json").read_bytes())
    assert manifest["round_start"] == 2
    assert manifest["rounds_after_swap"] == 0
    assert manifest["replaced_agent_id"] is None

    config = orjson.loads((prepared.new_run_dir / "replace_config.json").read_bytes())
    assert config["round_count"] == 2

    result = await resume_fork(prepared=prepared, monkeypatch=monkeypatch)

    # One advance per round, and none of them fresh: the clone's own
    # RoundAdvanced(2) is the one the resumed clock re-opened.
    assert rounds_advanced(result) == [(1, "simulation_start"), (2, "all_agents_idle")]

    # The truncation dropped round 2's injections, so the resume delivered them
    # again, after the boundary, to both agents.
    round_two_injections = [
        event
        for event in result.of_type(event_type="injection_delivered")
        if event["round_number"] == 2
    ]
    assert {event["agent_id"] for event in round_two_injections} == {
        FIRST_AGENT_ID,
        SECOND_AGENT_ID,
    }
    boundary_index = first_index(result, event_type="round_advanced", round_number=2)
    injection_index = first_index(result, event_type="injection_delivered", round_number=2)
    assert boundary_index < injection_index

    # Round 1 stays exactly as the source played it, and the run ends once.
    assert len([r for r, _ in rounds_advanced(result) if r == 1]) == 1
    ended = result.of_type(event_type="simulation_ended")
    assert len(ended) == 1
    assert ended[0] is result.events[-1] or ended[0]["round_number"] == 2

    # The fork's own messages reached the channel next to the source's.
    texts = {str(m["text"]) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)}
    assert "fork-first" in texts
    assert "src-first" in texts

    # A later --resume of this fork is crash recovery, not a second replay:
    # the log grew past the manifest's anchor, so the state comes from the
    # last message and no fresh advance is queued.
    recovered = await load_resume_state(
        run_dir=prepared.new_run_dir,
        events=await load_events(log_path=prepared.new_run_dir / "smoke.jsonl"),
    )
    assert recovered.enter_round_by_advancing is False
    assert recovered.round_number == 2


async def test_a_fork_after_the_final_round_advances_into_a_new_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After round 2 of a two-round source, the fork plays round 3, which the source never did.

    The clone holds no ``RoundAdvanced(3)`` and no ``SimulationEnded``, so the
    resumed clock records the advance fresh, briefs the agents for round 3, and
    ends the run there. Round 2 is not re-run: its verdict count stays one.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_fork(
        source_dir=source_dir,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=2,
        rounds_after=1,
    )

    manifest = orjson.loads((prepared.new_run_dir / "replace_manifest.json").read_bytes())
    assert manifest["round_start"] == 3
    assert manifest["rounds_after_swap"] == 0

    config = orjson.loads((prepared.new_run_dir / "replace_config.json").read_bytes())
    assert config["round_count"] == 3

    # The truncation cut the source's end marker, so the clone reads as a run
    # standing at the close of round 2.
    clone_lines = (prepared.new_run_dir / "smoke.jsonl").read_bytes().splitlines()
    clone_events = [orjson.loads(line) for line in clone_lines if line.strip()]
    assert all(event["event_type"] != "simulation_ended" for event in clone_events)
    assert (
        max(
            int(event["round_number"])
            for event in clone_events
            if event["event_type"] == "round_advanced"
        )
        == 2
    )

    result = await resume_fork(prepared=prepared, monkeypatch=monkeypatch)

    # The advance into round 3 was recorded fresh, exactly once, and marked as
    # the fork's own doing rather than an ordinary idle transition.
    assert rounds_advanced(result) == [
        (1, "simulation_start"),
        (2, "all_agents_idle"),
        (3, "fork_after_round"),
    ]

    # Round 3 was briefed after the fresh advance, to both agents.
    round_three_injections = [
        event
        for event in result.of_type(event_type="injection_delivered")
        if event["round_number"] == 3
    ]
    assert {event["agent_id"] for event in round_three_injections} == {
        FIRST_AGENT_ID,
        SECOND_AGENT_ID,
    }
    assert first_index(result, event_type="round_advanced", round_number=3) < first_index(
        result, event_type="injection_delivered", round_number=3
    )

    # Round 2 closed once, in the source; the fork did not re-judge it.
    round_two_endings = [
        event for event in result.of_type(event_type="round_ended") if event["round_number"] == 2
    ]
    assert len(round_two_endings) == 1

    # The run ends once, at the fork's own round.
    ended = result.of_type(event_type="simulation_ended")
    assert len(ended) == 1
    assert ended[0]["round_number"] == 3

    # The fork's messages landed in the new round.
    fork_messages = [
        m
        for m in result.messages_on(channel_id=LINK_CHANNEL_ID)
        if str(m["text"]).startswith("fork-")
    ]
    assert fork_messages
    assert all(int(m["round_number"]) == 3 for m in fork_messages)

    # A later --resume of this fork must not re-log the fork_after_round
    # advance: the log grew past the anchor, so recovery resumes from the
    # last message instead of re-deciding the advance from the manifest.
    recovered = await load_resume_state(
        run_dir=prepared.new_run_dir,
        events=await load_events(log_path=prepared.new_run_dir / "smoke.jsonl"),
    )
    assert recovered.enter_round_by_advancing is False
    assert recovered.round_number == 3


async def test_a_fork_clone_carries_no_stale_end_markers_or_inherited_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashed-then-recovered source's clone must read as a running run.

    A mid-log ``simulation_ended`` from a kill the source recovered from would
    trip every orchestration that gates evaluation on that event while the
    fork still runs. An inherited ``cross_run_replace_manifest.json`` is worse:
    the resume dispatch checks it first, so the fork would silently resume at
    the source's old boundary instead of the requested one.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)
    doctored_dir = tmp_path / "doctored"
    shutil.copytree(src=source_dir, dst=doctored_dir)

    log_path = doctored_dir / "smoke.jsonl"
    lines = log_path.read_bytes().splitlines()
    events = await load_events(log_path=log_path)
    first_advance = next(
        index for index, event in enumerate(events) if isinstance(event, RoundAdvanced)
    )
    stale_marker = SimulationEnded(
        round_number=1,
        reason=RunStatus.KILLED,
        total_messages=0,
        total_cost_usd=0.0,
    ).model_copy(update={"timestamp": events[first_advance].timestamp + timedelta(milliseconds=1)})
    lines.insert(first_advance + 1, stale_marker.model_dump_json().encode())
    log_path.write_bytes(b"\n".join(lines) + b"\n")

    (doctored_dir / "fork_manifest.json").write_bytes(b"{}")
    (doctored_dir / "imported_history_source.jsonl").write_bytes(b"{}")

    prepared = await prepare_fork(
        source_dir=doctored_dir,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        rounds_after=None,
    )

    clone_log = (prepared.new_run_dir / "smoke.jsonl").read_bytes()
    assert b'"simulation_ended"' not in clone_log
    assert not (prepared.new_run_dir / "fork_manifest.json").exists()
    assert not (prepared.new_run_dir / "imported_history_source.jsonl").exists()
    assert (prepared.new_run_dir / "replace_manifest.json").exists()


async def test_a_cross_run_source_cannot_be_forked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The imported agent's history cannot be rebuilt from the fork's own lineage.

    A cross-run run's log holds the original agent's turns before the import
    boundary and the imported agent's after it, under one agent_id. A fork
    rebuilding from that log would seed the seat with the agent that was
    explicitly replaced away, so the fork is refused.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)
    (source_dir / "cross_run_replace_manifest.json").write_bytes(b"{}")

    with pytest.raises(ValueError, match=r"is a cross-run replace-agent run"):
        await prepare_fork(
            source_dir=source_dir,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            after_round=1,
            rounds_after=None,
        )


async def test_a_fork_that_crashed_at_startup_anchors_at_the_boundary_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bookkeeping events past the anchor are a launch, not play.

    A launch appends re-registrations before any agent acts, so a fork that
    crashed there must not be treated as having played: recovering it from
    the last message would re-open the completed boundary round and replay
    its verdict.
    """
    source_dir = await make_source_run(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_fork(
        source_dir=source_dir,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=2,
        rounds_after=1,
    )

    log_path = prepared.new_run_dir / "smoke.jsonl"
    events = await load_events(log_path=log_path)
    registrations = [e for e in events if isinstance(e, AgentRegistered)]
    with log_path.open("a", encoding="utf-8") as handle:
        for registration in registrations:
            handle.write(registration.model_dump_json() + "\n")

    state = await load_resume_state(
        run_dir=prepared.new_run_dir,
        events=await load_events(log_path=log_path),
    )

    assert state.enter_round_by_advancing is True
    assert state.round_number == 2
