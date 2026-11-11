"""Importing an agent from another finished run, end to end.

A cross-run replace-agent run copies the target run (Sim A) up to the end of
round ``after_round`` and seats one of its agents with the history that agent
built in a different run (Sim B), cut at the end of ``source_b_round_end``.

The failure modes are silent. A history cut one round late hands the imported
agent turns it should not remember; one rebuilt from Sim A instead of Sim B
resumes the original agent under the import's name; a clone that keeps Sim A's
end marker reads as finished to every orchestration gating evaluation on it.
So the assertions are about the files the prepare step writes and the history
the resume rebuilds from them, not about whether the resume ran.
"""

from datetime import timedelta
from pathlib import Path
from typing import Any

import orjson
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart

from glossogen.models.event import (
    AgentRegistered,
    InjectionDelivered,
    RoundAdvanced,
    RunStatus,
    SimulationEnded,
    SimulationStarted,
)
from glossogen.run_derivation.cross_run_replace_agent import (
    CrossRunReplaceAgentRequest,
    prepare_cross_run_replace_agent_run,
)
from glossogen.run_derivation.run_launching import PreparedForkRun
from glossogen.run_replay.resume_state_loader import load_resume_state
from glossogen.run_storage.event_log_reader import load_events
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
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

SOURCE_ROUND_COUNT = 2
IMPORTED_MODEL = "claude-haiku-4-5"
IMPORTED_PROVIDER = "anthropic"


def speak_then_idle(*, text: str) -> list[ScriptedTurn]:
    """One send, then park until the next round wakes the agent."""
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
        ),
        ToolTurn(tool_name="read_notifications", args={}),
        SayTurn(text="idle"),
    ]


def speak_each_round(*, prefix: str) -> list[PacedTurn]:
    """One send per source round, tagged with its round: ``<prefix>-r1``, ``<prefix>-r2``.

    Each send sits behind a ``RoundGate``, so the round a message lands in is
    the script's statement rather than the scheduler's choice. The round cutoff
    of Sim B's history is only observable when it is.
    """
    turns: list[PacedTurn] = []
    for round_number in range(1, SOURCE_ROUND_COUNT + 1):
        turns.append(RoundGate(round_number=round_number))
        turns.append(
            ToolTurn(
                tool_name="send_message",
                args={
                    "channel_id": LINK_CHANNEL_ID,
                    "text": f"{prefix}-r{round_number}",
                    "force": True,
                },
            )
        )
        turns.append(SayTurn(text="done"))
    return turns


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
    run_dir: Path,
    tag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Run a two-round source to completion, its sends tagged ``<tag>-<agent>-r<round>``."""
    run_dir.mkdir(parents=True)
    result = await run_round_paced_simulation(
        scenario=build_scenario(round_count=SOURCE_ROUND_COUNT),
        scripts={
            FIRST_AGENT_ID: speak_each_round(prefix=f"{tag}-first"),
            SECOND_AGENT_ID: speak_each_round(prefix=f"{tag}-second"),
        },
        tmp_path=run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    assert result.of_type(event_type=SimulationEnded), f"source {tag} did not finish"
    sent_rounds = {
        str(m.text): int(m.round_number) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)
    }
    assert sent_rounds[f"{tag}-first-r1"] == 1
    assert sent_rounds[f"{tag}-first-r2"] == 2
    return run_dir


async def make_sources(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Sim A (the target, sends tagged ``a``) and Sim B (the import's origin, tagged ``b``)."""
    sim_a = await make_source_run(run_dir=tmp_path / "sim_a", tag="a", monkeypatch=monkeypatch)
    sim_b = await make_source_run(run_dir=tmp_path / "sim_b", tag="b", monkeypatch=monkeypatch)
    return sim_a, sim_b


async def prepare_import(
    *,
    sim_a: Path,
    sim_b: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_round: int,
    source_b_round_end: int,
    provider: str,
    knobs: dict[str, Any] | None,
) -> PreparedForkRun:
    """Import Sim B's first agent into Sim A on disk, without launching anything.

    The smoke scenario is registered nowhere, so the scenario lookup is pointed
    at it directly, and the credential preflight gets a stub key.
    """

    def smoke_class(name: str) -> type[SmokeScenario]:
        assert name == "smoke"
        return SmokeScenario

    monkeypatch.setattr(
        "glossogen.run_derivation.cross_run_replace_agent.get_scenario_class", smoke_class
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return await prepare_cross_run_replace_agent_run(
        request=CrossRunReplaceAgentRequest(
            source_a_run_dir=sim_a,
            source_b_run_dir=sim_b,
            scenario_name="smoke",
            after_round=after_round,
            source_b_round_end=source_b_round_end,
            rounds_after=None,
            replaced_agent_id=FIRST_AGENT_ID,
            model=IMPORTED_MODEL,
            provider=provider,
            knobs=knobs,
            channels_with_visible_history=[LINK_CHANNEL_ID],
            runs_dir=tmp_path / "runs",
        )
    )


def sent_texts(*, history: list[ModelMessage]) -> list[str]:
    """The ``send_message`` texts an agent's rebuilt history remembers sending, in order."""
    texts: list[str] = []
    for message in history:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, ToolCallPart) and part.tool_name == "send_message":
                texts.append(str(part.args_as_dict()["text"]))
    return texts


async def test_the_prepared_run_records_both_sources_and_cuts_sim_b_at_its_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The new run holds Sim A up to the boundary, Sim B verbatim, and a manifest tying them."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )
    new_dir = prepared.new_run_dir
    sim_b_events = await load_events(log_path=sim_b / "smoke.jsonl")
    sim_b_round_two = next(
        e for e in sim_b_events if isinstance(e, RoundAdvanced) and e.round_number == 2
    )

    manifest = orjson.loads((new_dir / "cross_run_replace_manifest.json").read_bytes())
    assert manifest["source_a_run_id"] == "smoke/sim_a"
    assert manifest["source_b_run_id"] == "smoke/sim_b"
    assert manifest["round_start"] == 2
    assert manifest["rounds_after_swap"] == 0
    assert manifest["source_b_round_end"] == 1
    assert manifest["source_b_cutoff_event_id"] == sim_b_round_two.event_id
    assert manifest["replaced_agent_id"] == FIRST_AGENT_ID
    assert manifest["imported_model"] == IMPORTED_MODEL
    assert manifest["imported_provider"] == IMPORTED_PROVIDER
    assert manifest["channels_with_visible_history"] == [LINK_CHANNEL_ID]
    assert manifest["blocked_tool_call_channels"] == []
    assert not (new_dir / "replace_manifest.json").exists()

    # Sim B is copied byte for byte: the resume cuts it, not the prepare step.
    assert (new_dir / "imported_history_source.jsonl").read_bytes() == (
        sim_b / "smoke.jsonl"
    ).read_bytes()

    # The clone is Sim A standing at the start of round 2, under the new run's id.
    clone_events = await load_events(log_path=new_dir / "smoke.jsonl")
    assert not [e for e in clone_events if isinstance(e, SimulationEnded)]
    assert isinstance(clone_events[-1], RoundAdvanced)
    assert clone_events[-1].round_number == 2
    clone_texts = (new_dir / "smoke.jsonl").read_text()
    assert "a-first-r1" in clone_texts
    assert "a-first-r2" not in clone_texts
    assert "b-first" not in clone_texts

    # The imported seat runs on the requested model; the other keeps Sim A's.
    sim_a_events = await load_events(log_path=sim_a / "smoke.jsonl")
    second_registration = next(
        e for e in sim_a_events if isinstance(e, AgentRegistered) and e.agent_id == SECOND_AGENT_ID
    )
    config = orjson.loads((new_dir / "replace_config.json").read_bytes())
    assert config["round_count"] == 2
    assert config["model_overrides"] == {
        FIRST_AGENT_ID: {"model": IMPORTED_MODEL, "provider": IMPORTED_PROVIDER},
        SECOND_AGENT_ID: {
            "model": second_registration.model,
            "provider": second_registration.provider,
        },
    }
    started = clone_events[0]
    assert isinstance(started, SimulationStarted)
    assert started.run_id == prepared.new_run_id
    assert started.scenario_config == config

    assert prepared.launch_cmd[-4:] == (
        "--resume",
        str(new_dir),
        "--config",
        str(new_dir / "replace_config.json"),
    )


async def test_the_imported_seat_remembers_sim_b_up_to_its_cutoff_and_nothing_of_sim_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resume seeds the imported agent from Sim B's round 1 and the other agent from Sim A's."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )

    state = await load_resume_state(
        run_dir=prepared.new_run_dir,
        events=await load_events(log_path=prepared.new_run_dir / "smoke.jsonl"),
    )

    assert state.round_number == 2
    assert state.enter_round_by_advancing is False
    assert state.replaced_agent_ids == frozenset({FIRST_AGENT_ID})
    imported = state.agent_message_histories[FIRST_AGENT_ID]
    assert sent_texts(history=imported) == ["b-first-r1"]
    other = state.agent_message_histories[SECOND_AGENT_ID]
    assert sent_texts(history=other) == ["a-second-r1"]

    # The channel the agents share carries Sim A's round 1, not Sim B's.
    channel_texts = [str(m.text) for m in state.messages_by_channel[LINK_CHANNEL_ID]]
    assert sorted(channel_texts) == ["a-first-r1", "a-second-r1"]


async def test_a_sim_b_cut_at_its_final_round_imports_every_round_it_played(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sim B has no ``RoundAdvanced`` past its last round, so the cut falls at its last event."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=SOURCE_ROUND_COUNT,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )

    manifest = orjson.loads((prepared.new_run_dir / "cross_run_replace_manifest.json").read_bytes())
    assert manifest["source_b_cutoff_event_id"] == ""

    state = await load_resume_state(
        run_dir=prepared.new_run_dir,
        events=await load_events(log_path=prepared.new_run_dir / "smoke.jsonl"),
    )
    assert sent_texts(history=state.agent_message_histories[FIRST_AGENT_ID]) == [
        "b-first-r1",
        "b-first-r2",
    ]


async def test_a_resumed_import_plays_the_entry_round_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resume re-opens round 2, briefs both seats and ends once, keeping Sim A's round 1."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )
    config: dict[str, Any] = orjson.loads(
        (prepared.new_run_dir / "replace_config.json").read_bytes()
    )

    result: SimulationResult = await resume_simulation(
        scenario=SmokeScenario(knobs=SmokeKnobs.model_validate(config)),
        scripts={
            FIRST_AGENT_ID: speak_then_idle(text="fork-first"),
            SECOND_AGENT_ID: speak_then_idle(text="fork-second"),
        },
        run_dir=prepared.new_run_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    advances = [
        (int(e.round_number), str(e.trigger)) for e in result.of_type(event_type=RoundAdvanced)
    ]
    assert advances == [(1, "simulation_start"), (2, "all_agents_idle")]
    round_two_injections = [
        e for e in result.of_type(event_type=InjectionDelivered) if e.round_number == 2
    ]
    assert {e.agent_id for e in round_two_injections} == {FIRST_AGENT_ID, SECOND_AGENT_ID}
    ended = result.of_type(event_type=SimulationEnded)
    assert len(ended) == 1

    rounds_by_text = {
        str(m.text): int(m.round_number) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)
    }
    assert rounds_by_text["a-first-r1"] == 1
    assert rounds_by_text["fork-first"] == 2
    assert rounds_by_text["fork-second"] == 2
    assert not [text for text in rounds_by_text if text.startswith("b-")]


async def test_a_stale_end_marker_in_sim_a_does_not_reach_the_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Sim A that was killed and recovered holds a ``simulation_ended`` mid-log.

    Kept in the clone, it would read as finished to every orchestration that
    gates evaluation on that event while the import is still running.
    """
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    log_path = sim_a / "smoke.jsonl"
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

    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )

    assert b'"simulation_ended"' not in (prepared.new_run_dir / "smoke.jsonl").read_bytes()


async def test_a_sim_b_channel_sim_a_lacks_is_blocked_in_the_imported_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool calls on a channel only Sim B had would name a channel the resumed runtime lacks.

    The manifest lists such channels so the resume drops those calls from the
    imported agent's history. Channels both runs share stay unblocked.
    """
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    log_path = sim_b / "smoke.jsonl"
    lines = log_path.read_bytes().splitlines()
    for index, line in enumerate(lines):
        event = orjson.loads(line)
        if event["event_type"] == "agent_registered" and event["agent_id"] == FIRST_AGENT_ID:
            event["channel_ids"] = [*event["channel_ids"], "backroom"]
            lines[index] = orjson.dumps(event)
    log_path.write_bytes(b"\n".join(lines) + b"\n")

    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs=None,
    )

    manifest = orjson.loads((prepared.new_run_dir / "cross_run_replace_manifest.json").read_bytes())
    assert manifest["blocked_tool_call_channels"] == ["backroom"]


async def test_a_knobs_round_count_sets_how_many_rounds_the_import_plays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--knobs`` merge over Sim A's config; a round_count of 3 plays rounds 2 and 3."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    prepared = await prepare_import(
        sim_a=sim_a,
        sim_b=sim_b,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        after_round=1,
        source_b_round_end=1,
        provider=IMPORTED_PROVIDER,
        knobs={"round_count": 3, "max_round_duration_seconds": 30},
    )

    config = orjson.loads((prepared.new_run_dir / "replace_config.json").read_bytes())
    assert config["round_count"] == 3
    assert config["max_round_duration_seconds"] == 30
    manifest = orjson.loads((prepared.new_run_dir / "cross_run_replace_manifest.json").read_bytes())
    assert manifest["round_start"] == 2
    assert manifest["rounds_after_swap"] == 1


@pytest.mark.parametrize(
    ("source_b_round_end", "provider", "message"),
    [
        (SOURCE_ROUND_COUNT + 1, IMPORTED_PROVIDER, r"Source B did not reach round 3"),
        (0, IMPORTED_PROVIDER, r"source_b_round_end must be >= 1"),
        (1, "no-such-provider", r"Unknown provider"),
    ],
)
async def test_an_import_the_sources_cannot_support_is_refused_before_a_run_dir_is_claimed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_b_round_end: int,
    provider: str,
    message: str,
) -> None:
    """A refused import leaves no half-written run directory for a sweep to pick up."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    with pytest.raises(ValueError, match=message):
        await prepare_import(
            sim_a=sim_a,
            sim_b=sim_b,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            after_round=1,
            source_b_round_end=source_b_round_end,
            provider=provider,
            knobs=None,
        )
    assert not (tmp_path / "runs").exists()


async def test_an_import_from_a_run_of_another_scenario_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent ids and channels mean nothing across scenarios, so Sim B must share Sim A's."""
    sim_a, sim_b = await make_sources(tmp_path=tmp_path, monkeypatch=monkeypatch)
    log_path = sim_b / "smoke.jsonl"
    lines = log_path.read_bytes().splitlines()
    started = orjson.loads(lines[0])
    started["scenario_name"] = "other"
    lines[0] = orjson.dumps(started)
    log_path.write_bytes(b"\n".join(lines) + b"\n")

    with pytest.raises(ValueError, match=r"Scenario mismatch"):
        await prepare_import(
            sim_a=sim_a,
            sim_b=sim_b,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            after_round=1,
            source_b_round_end=1,
            provider=IMPORTED_PROVIDER,
            knobs=None,
        )
    assert not (tmp_path / "runs").exists()
