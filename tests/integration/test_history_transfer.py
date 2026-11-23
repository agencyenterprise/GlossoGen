"""Seating a new run's agents with the histories agents built in another finished run.

A history-transfer run is a fresh run in which chosen seats start with a source
agent's history, cut at the end of a source round, followed by one message that
opens the new run. The seat id and the source agent id may differ, because the
source may be a run of another scenario; these tests seat the source's first
agent in the new run's second seat so that a mix-up between the two ids shows.

The failure modes are silent. A history cut one round late hands the seat turns
it should not remember. A history the runner follows with its continuation
prompt asks the model to carry on a session it was just told had ended. A
resumed run that rebuilds the seat from its own log alone forgets the source
entirely. So the assertions are about what the seat's model is sent.
"""

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import NamedTuple

import orjson
import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import AgentSwappedMidRun, SimulationEnded, SimulationEvent
from glossogen.run_derivation.history_transfer import (
    HistoryTransferPlan,
    HistoryTransferRequest,
    plan_history_transfer,
    prepare_history_transfer,
)
from glossogen.run_replay.resume_state_loader import load_resume_state
from glossogen.run_replay.transferred_history import (
    build_source_history,
    read_transferred_history,
    splice_transferred_histories,
    with_transferred_history,
)
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.history_transfer_manifest import read_history_transfer_manifest
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_contract.platform_runner_prompts import platform_runner_prompts
from glossogen.testing import simulation_harness
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out, run_simulation
from glossogen.testing.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeScenario,
)
from tests.fakes.tagged_source_runs import (
    SOURCE_ROUND_COUNT,
    build_smoke_scenario,
    make_tagged_source_run,
    sent_texts,
)

SCENARIO_NAME = "smoke"
SEAT_ID = SECOND_AGENT_ID
SOURCE_AGENT_ID = FIRST_AGENT_ID
TARGET_SEND = ToolTurn(
    tool_name="send_message",
    args={"channel_id": LINK_CHANNEL_ID, "text": "target-second-r1", "force": True},
)
# Captured at import, so a test that wraps the harness's builder wraps the real one.
BUILD_SCRIPTED_MODEL = simulation_harness.build_scripted_model


async def make_source(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A finished two-round source run whose sends are tagged ``src-<agent>-r<round>``."""
    return await make_tagged_source_run(
        run_dir=tmp_path / SCENARIO_NAME / "source", tag="src", monkeypatch=monkeypatch
    )


async def plan_seat(*, source_run_dir: Path, source_round_end: int | None) -> HistoryTransferPlan:
    """Plan seating the target's second seat with the source's first agent."""
    return await plan_history_transfer(
        request=HistoryTransferRequest(
            source_run_dir=source_run_dir,
            source_scenario_name=SCENARIO_NAME,
            seat_sources={SEAT_ID: SOURCE_AGENT_ID},
            source_round_end=source_round_end,
        ),
        seat_ids=[FIRST_AGENT_ID, SECOND_AGENT_ID],
    )


async def prepare_seat(
    *, plan: HistoryTransferPlan, run_dir: Path, scenario: SmokeScenario
) -> dict[str, list[ModelMessage]]:
    """Build and save the planned history into ``run_dir`` for ``scenario``'s agents."""
    run_dir.mkdir(parents=True, exist_ok=True)
    return await prepare_history_transfer(
        plan=plan,
        run_dir=run_dir,
        scenario=scenario,
        agents=scenario.get_agents(default_model="scripted-model", default_provider="anthropic"),
    )


def system_prompts(*, history: Sequence[ModelMessage]) -> list[str]:
    """Every system prompt in ``history``, in order."""
    return [
        part.content
        for message in history
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, SystemPromptPart)
    ]


def user_prompts(*, message: ModelMessage) -> list[str]:
    """The user prompts of one message."""
    if not isinstance(message, ModelRequest):
        return []
    return [str(part.content) for part in message.parts if isinstance(part, UserPromptPart)]


class FirstRequestRecorder:
    """Wraps a scripted model and records the messages of every request it is sent."""

    def __init__(self, scripted: FunctionModel) -> None:
        self._scripted = scripted
        self.requests: list[list[ModelMessage]] = []

    def model(self) -> FunctionModel:
        """Return the wrapping model."""

        async def stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
            self.requests.append(list(messages))
            assert self._scripted.stream_function is not None
            async for chunk in self._scripted.stream_function(messages, info):
                yield chunk

        return FunctionModel(stream_function=stream)


class RecordedScript(NamedTuple):
    """One scripted agent's opening turn and the recorder wrapping its model."""

    first_turn: ScriptedTurn
    recorder: FirstRequestRecorder


def record_every_script(*, monkeypatch: pytest.MonkeyPatch) -> list[RecordedScript]:
    """Record the requests of every scripted agent, told apart by their opening turn."""
    recorded: list[RecordedScript] = []

    def build_recorded(
        *, turns: Sequence[ScriptedTurn], when_exhausted: Sequence[ScriptedTurn] | None
    ) -> FunctionModel:
        scripted = BUILD_SCRIPTED_MODEL(turns=turns, when_exhausted=when_exhausted)
        recorder = FirstRequestRecorder(scripted=scripted)
        recorded.append(RecordedScript(first_turn=turns[0], recorder=recorder))
        return recorder.model()

    monkeypatch.setattr(simulation_harness, "build_scripted_model", build_recorded)
    return recorded


def first_request_of(
    *, recorded: list[RecordedScript], first_turn: ScriptedTurn
) -> list[ModelMessage]:
    """The first request sent to the one agent whose script opens with ``first_turn``."""
    matches = [entry.recorder for entry in recorded if entry.first_turn == first_turn]
    assert len(matches) == 1
    return matches[0].requests[0]


async def test_a_seat_starts_with_its_source_agents_turns_up_to_the_cut_then_the_new_runs_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 of the source is kept, round 2 is not, and the new run's prompts close it."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target = build_smoke_scenario(round_count=1)

    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=1),
        run_dir=tmp_path / "target",
        scenario=target,
    )

    assert sorted(histories) == [SEAT_ID]
    history = histories[SEAT_ID]
    assert sent_texts(history=history) == ["src-first-r1"]
    assert system_prompts(history=history)[0].startswith(f"You are {SOURCE_AGENT_ID}.")
    assert len(system_prompts(history=history)) == 1
    opening = user_prompts(message=history[-1])
    assert len(opening) == 1
    seat_prompt = next(
        agent.system_prompt
        for agent in target.get_agents(default_model="m", default_provider="anthropic")
        if agent.agent_id == SEAT_ID
    )
    assert f"You are {SEAT_ID}." in seat_prompt
    assert seat_prompt in opening[0]
    assert opening[0].endswith(platform_runner_prompts(role_name=SEAT_ID).initial)


async def test_with_no_round_named_a_finished_source_is_kept_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every round the source played reaches the seat."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)

    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=None),
        run_dir=tmp_path / "target",
        scenario=build_smoke_scenario(round_count=1),
    )

    assert sent_texts(history=histories[SEAT_ID]) == ["src-first-r1", "src-first-r2"]


async def test_the_manifest_names_the_source_and_the_saved_history_reads_back_as_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume reads the seat's history from disk, so the file must be the history."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target_dir = tmp_path / "target"

    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=1),
        run_dir=target_dir,
        scenario=build_smoke_scenario(round_count=1),
    )

    manifest = read_history_transfer_manifest(run_dir=target_dir)
    assert manifest is not None
    assert manifest.source_run_id == f"{SCENARIO_NAME}/source"
    assert manifest.source_round_end == 1
    assert [(seat.agent_id, seat.source_agent_id) for seat in manifest.seats] == [
        (SEAT_ID, SOURCE_AGENT_ID)
    ]
    saved = await read_transferred_history(path=target_dir / manifest.seats[0].history_file)
    assert saved == histories[SEAT_ID]


async def test_the_seat_is_sent_its_history_and_opening_message_without_a_continuation_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seat is first sent its saved history; the other seat starts fresh.

    pydantic-ai merges the opening message into a request the source history ends
    with, such as a last tool result, so the check is on the last request's user
    prompts: the opening message alone, with no continuation prompt after it.
    """
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target = build_smoke_scenario(round_count=1)
    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=1),
        run_dir=tmp_path / "target",
        scenario=target,
    )
    scenario_agents = target.get_agents

    def agents_with_histories(default_model: str, default_provider: str) -> list[AgentConfig]:
        agents = scenario_agents(default_model=default_model, default_provider=default_provider)
        for agent in agents:
            agent.initial_message_history = histories.get(agent.agent_id)
        return agents

    monkeypatch.setattr(target, "get_agents", agents_with_histories)
    recorded = record_every_script(monkeypatch=monkeypatch)
    fresh_first_turn = SayTurn(text="fresh seat idle")

    result = await run_simulation(
        scenario=target,
        scripts={
            SEAT_ID: [TARGET_SEND, SayTurn(text="done")],
            FIRST_AGENT_ID: [fresh_first_turn],
        },
        tmp_path=tmp_path / "target_run",
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert result.of_type(event_type=SimulationEnded)
    assert [str(m.text) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)] == [
        "target-second-r1"
    ]
    seat_request = first_request_of(recorded=recorded, first_turn=TARGET_SEND)
    assert system_prompts(history=seat_request)[0].startswith(f"You are {SOURCE_AGENT_ID}.")
    assert sent_texts(history=seat_request) == ["src-first-r1"]
    assert user_prompts(message=seat_request[-1]) == user_prompts(message=histories[SEAT_ID][-1])
    fresh_request = first_request_of(recorded=recorded, first_turn=fresh_first_turn)
    assert len(fresh_request) == 1
    assert system_prompts(history=fresh_request)[0].startswith(f"You are {FIRST_AGENT_ID}.")


async def test_a_resumed_transfer_run_puts_the_saved_history_before_the_seats_own_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume rebuilds the seat from the log, which holds only its turns in this run."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = build_smoke_scenario(round_count=1)
    await run_simulation(
        scenario=target,
        scripts={SEAT_ID: [TARGET_SEND, SayTurn(text="done")], FIRST_AGENT_ID: []},
        tmp_path=target_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=1),
        run_dir=target_dir,
        scenario=target,
    )

    events = await load_events(
        log_path=event_log_path(run_dir=target_dir, scenario_name=SCENARIO_NAME)
    )
    state = await load_resume_state(run_dir=target_dir, events=events)

    seat_history = state.agent_message_histories[SEAT_ID]
    transferred = histories[SEAT_ID]
    assert seat_history[: len(transferred)] == transferred
    assert isinstance(seat_history[len(transferred)], ModelResponse)
    assert sent_texts(history=seat_history) == ["src-first-r1", "target-second-r1"]
    assert len(system_prompts(history=seat_history)) == 1
    other_history = state.agent_message_histories[FIRST_AGENT_ID]
    assert system_prompts(history=other_history)[0].startswith(f"You are {FIRST_AGENT_ID}.")
    assert sent_texts(history=other_history) == []


def rewrite_end_marker(*, log_path: Path, reason: str | None) -> None:
    """Drop the source log's ``simulation_ended``, or rewrite its reason to ``reason``."""
    kept: list[bytes] = []
    for line in log_path.read_bytes().splitlines():
        if not line.strip():
            continue
        event = orjson.loads(line)
        if event["event_type"] == "simulation_ended":
            if reason is None:
                continue
            event["reason"] = reason
            line = orjson.dumps(event)
        kept.append(line)
    log_path.write_bytes(b"\n".join(kept) + b"\n")


async def make_target_with_transfer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, list[SimulationEvent], dict[str, list[ModelMessage]]]:
    """A finished one-round target run whose second seat got the source's first agent's history."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = build_smoke_scenario(round_count=1)
    await run_simulation(
        scenario=target,
        scripts={SEAT_ID: [TARGET_SEND, SayTurn(text="done")], FIRST_AGENT_ID: []},
        tmp_path=target_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )
    histories = await prepare_seat(
        plan=await plan_seat(source_run_dir=source, source_round_end=1),
        run_dir=target_dir,
        scenario=target,
    )
    events = await load_events(
        log_path=event_log_path(run_dir=target_dir, scenario_name=SCENARIO_NAME)
    )
    return target_dir, events, histories


async def test_the_probes_see_a_seats_transferred_history_and_nothing_extra_for_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe rebuilds from the run's log, which lacks the history the seat started with."""
    target_dir, events, histories = await make_target_with_transfer(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    state = await load_resume_state(run_dir=target_dir, events=events)
    own_seat = [
        ModelRequest(parts=[UserPromptPart(content="own opening")]),
        *state.agent_message_histories[SEAT_ID][len(histories[SEAT_ID]) :],
    ]
    other = state.agent_message_histories[FIRST_AGENT_ID]

    seat_history = await with_transferred_history(
        run_dir=target_dir, events=events, agent_id=SEAT_ID, own_history=own_seat
    )
    other_history = await with_transferred_history(
        run_dir=target_dir, events=events, agent_id=FIRST_AGENT_ID, own_history=other
    )

    assert seat_history == state.agent_message_histories[SEAT_ID]
    assert other_history == other


async def test_a_seat_swapped_in_run_is_rebuilt_without_the_transferred_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent that an in-run swap put in the seat never held the transferred history."""
    target_dir, events, _ = await make_target_with_transfer(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    swap = AgentSwappedMidRun(
        round_number=1,
        agent_id=SEAT_ID,
        new_model="claude-haiku-5-5",
        new_provider="anthropic",
        channel_visibility={},
    )
    state = await load_resume_state(run_dir=target_dir, events=events)
    own_only = state._replace(agent_message_histories={})
    rebuilt = await load_resume_state(run_dir=target_dir, events=[*events, swap])

    spliced = await splice_transferred_histories(
        run_dir=target_dir, events=[*events, swap], state=own_only
    )

    assert SEAT_ID not in spliced.agent_message_histories
    assert sent_texts(history=rebuilt.agent_message_histories[SEAT_ID]) == ["target-second-r1"]


async def test_a_source_without_its_end_marker_keeps_only_rounds_it_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that did not finish has not completed its last round; earlier rounds still count."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    rewrite_end_marker(
        log_path=event_log_path(run_dir=source, scenario_name=SCENARIO_NAME), reason=None
    )

    with pytest.raises(ValueError, match=r"opened round 2 but never finished it"):
        await plan_seat(source_run_dir=source, source_round_end=None)
    with pytest.raises(ValueError, match=r"opened round 2 but never finished it"):
        await plan_seat(source_run_dir=source, source_round_end=SOURCE_ROUND_COUNT)
    plan = await plan_seat(source_run_dir=source, source_round_end=1)
    assert plan.source_round_end == 1


@pytest.mark.parametrize("reason", ["killed", "error"])
async def test_a_source_that_was_stopped_keeps_only_rounds_it_completed(
    reason: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A killed or errored source may have stopped partway through its last round."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    rewrite_end_marker(
        log_path=event_log_path(run_dir=source, scenario_name=SCENARIO_NAME), reason=reason
    )

    with pytest.raises(ValueError, match=rf"ended with reason '{reason}'"):
        await plan_seat(source_run_dir=source, source_round_end=None)
    plan = await plan_seat(source_run_dir=source, source_round_end=1)
    assert plan.source_round_end == 1


async def test_a_cut_before_the_last_round_leaves_out_the_next_rounds_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A call made in round 1 whose result came back in round 2 is not part of round 1."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)

    cut = await plan_seat(source_run_dir=source, source_round_end=1)
    whole = await plan_seat(source_run_dir=source, source_round_end=None)

    def round_two_results(plan: HistoryTransferPlan) -> list[str]:
        history = build_source_history(
            source_events=plan.source_events,
            source_agent_id=SOURCE_AGENT_ID,
            keep_thinking=True,
            split_parallel_tool_calls=False,
        )
        return [
            str(part.content)
            for message in history
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart) and '"current_round": 2' in str(part.content)
        ]

    assert round_two_results(plan=cut) == []
    assert round_two_results(plan=whole) != []


async def test_a_source_agent_with_no_turns_is_refused_before_a_directory_is_claimed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seat cannot start with an empty source history, and planning says so."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    log_path = event_log_path(run_dir=source, scenario_name=SCENARIO_NAME)
    agent_turn_events = {"llm_response_received", "tool_call_invoked", "tool_result_received"}
    kept_lines = [
        line
        for line in log_path.read_bytes().splitlines()
        if line.strip()
        and not (
            orjson.loads(line)["event_type"] in agent_turn_events
            and orjson.loads(line).get("agent_id") == SOURCE_AGENT_ID
        )
    ]
    log_path.write_bytes(b"\n".join(kept_lines) + b"\n")

    with pytest.raises(ValueError, match=r"source agent 'first_agent' took no turn"):
        await plan_seat(source_run_dir=source, source_round_end=1)


@pytest.mark.parametrize(
    ("seat_sources", "source_round_end", "message"),
    [
        ({}, 1, r"name at least one seat"),
        ({"no_such_seat": SOURCE_AGENT_ID}, 1, r"\['no_such_seat'\] are not agents of this run"),
        ({SEAT_ID: "no_such_agent"}, 1, r"agent 'no_such_agent' is not in source run"),
        ({SEAT_ID: SOURCE_AGENT_ID}, SOURCE_ROUND_COUNT + 1, r"never completed round 3"),
        ({SEAT_ID: SOURCE_AGENT_ID}, 0, r"must be >= 1"),
    ],
)
async def test_a_transfer_the_source_cannot_support_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    seat_sources: dict[str, str],
    source_round_end: int,
    message: str,
) -> None:
    """Each refusal happens at planning, before the new run claims a directory."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)

    with pytest.raises(ValueError, match=message):
        await plan_history_transfer(
            request=HistoryTransferRequest(
                source_run_dir=source,
                source_scenario_name=SCENARIO_NAME,
                seat_sources=seat_sources,
                source_round_end=source_round_end,
            ),
            seat_ids=[FIRST_AGENT_ID, SECOND_AGENT_ID],
        )


async def test_a_source_of_another_scenario_than_named_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log found under the named scenario must be a run of that scenario."""
    source = await make_source(tmp_path=tmp_path, monkeypatch=monkeypatch)
    log_path = event_log_path(run_dir=source, scenario_name=SCENARIO_NAME)
    log_path.rename(event_log_path(run_dir=source, scenario_name="veyru"))

    with pytest.raises(ValueError, match=r"is a 'smoke' run, not 'veyru'"):
        await plan_history_transfer(
            request=HistoryTransferRequest(
                source_run_dir=source,
                source_scenario_name="veyru",
                seat_sources={SEAT_ID: SOURCE_AGENT_ID},
                source_round_end=1,
            ),
            seat_ids=[FIRST_AGENT_ID, SECOND_AGENT_ID],
        )
