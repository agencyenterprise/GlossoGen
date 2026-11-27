"""``record_token_ids`` logs each self-hosted response's token ids and logprobs, and they read back.

The runner stores each prompt as the prefix it shares with the agent's previous recorded
prompt and answer, then the rest of its ids. ``recorded_token_ids`` rebuilds the full
prompts from the event log.
"""

import asyncio
from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.llm.self_hosted_chat_model import (
    PROMPT_TOKEN_IDS_DETAIL,
    TOKEN_IDS_DETAIL,
    TOKEN_LOGPROBS_DETAIL,
)
from glossogen.models.event import (
    LLMResponseReceived,
    SimulationEvent,
    SimulationStarted,
    StopReason,
    core_event_types,
)
from glossogen.models.event_base import TokenUsage
from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.recorded_token_ids import (
    RecordedTokenIds,
    TokenIdLogGap,
    TokenLogprobCountMismatch,
    recorded_token_ids,
)
from glossogen.runners.pydantic_ai_runner import (
    _StreamingState,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.runners.pydantic_ai_runner import (
    PydanticAIRunner,
)
from glossogen.runners.token_id_log import TokenIdLog
from glossogen.runtime.event_bus import EventBus
from glossogen.runtime.event_logger import EventLogger

AGENT = "player_a"
RUN_ID = "signal_game/1"


class ServedResponse(NamedTuple):
    """One response as the server returned it: its prompt's and its answer's token ids, and the
    logprob of each answer token."""

    prompt_ids: list[int]
    token_ids: list[int]
    token_logprobs: list[float]


def logprobs_for(token_ids: list[int]) -> list[float]:
    """A distinct logprob for each answer token."""
    return [-0.25 * (index + 1) for index in range(len(token_ids))]


def _usage() -> TokenUsage:
    return TokenUsage(
        input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


async def log_responses(log_path: Path, runs: list[list[ServedResponse | None]], text: str) -> None:
    """Log each response through the runner's flush; each inner list is one runner's life.

    ``None`` is a response that carried no token ids, and ``text`` is each response's text.
    """
    runner = PydanticAIRunner(
        max_turns=1,
        event_bus=EventBus(max_queue_size=8),
        run_id=RUN_ID,
        scenario_name="signal_game",
        telemetry_enabled=False,
    )
    event_logger = EventLogger(
        log_path=log_path,
        event_bus=EventBus(max_queue_size=64),
        allowed_event_types=frozenset(core_event_types()),
    )
    await event_logger.open()
    await event_logger.log(
        event=SimulationStarted(
            round_number=0,
            run_id=RUN_ID,
            scenario_name="signal_game",
            scenario_description="",
            channel_ids=[],
            scenario_config={},
            provider="self-hosted",
        )
    )
    for responses in runs:
        token_id_log = TokenIdLog()
        for response in responses:
            state = _StreamingState(token_id_log=token_id_log)
            state.accumulated_text = text
            if response is not None:
                state.note_token_ids(
                    details={
                        PROMPT_TOKEN_IDS_DETAIL: response.prompt_ids,
                        TOKEN_IDS_DETAIL: response.token_ids,
                        TOKEN_LOGPROBS_DETAIL: response.token_logprobs,
                    }
                )
            runner._flush_response_block(  # pyright: ignore[reportPrivateUsage]
                agent_id=AGENT,
                state=state,
                event_logger=event_logger,
                stop_reason=StopReason.END_TURN,
                round_number=1,
                usage=_usage(),
            )
            await asyncio.gather(*state.background_tasks)
    await event_logger.close()


def logged_responses(events: list[SimulationEvent]) -> list[LLMResponseReceived]:
    return [event for event in events if isinstance(event, LLMResponseReceived)]


async def test_each_recorded_prompt_is_rebuilt_whole(tmp_path: Path) -> None:
    """The second prompt repeats the first prompt and answer; the third drops the answer."""
    served = [
        ServedResponse(
            prompt_ids=[1, 2, 3], token_ids=[4, 5], token_logprobs=logprobs_for(token_ids=[4, 5])
        ),
        ServedResponse(
            prompt_ids=[1, 2, 3, 4, 5, 6, 7],
            token_ids=[8],
            token_logprobs=logprobs_for(token_ids=[8]),
        ),
        ServedResponse(
            prompt_ids=[1, 2, 9],
            token_ids=[10, 11],
            token_logprobs=logprobs_for(token_ids=[10, 11]),
        ),
    ]
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(text="I move left.", log_path=log_path, runs=[list(served)])

    events = await load_events(log_path=log_path)
    logged = logged_responses(events=events)
    assert [(each.prompt_prefix_tokens, each.prompt_tail_ids) for each in logged] == [
        (0, [1, 2, 3]),
        (5, [6, 7]),
        (2, [9]),
    ]
    rebuilt = recorded_token_ids(events=events, agent_id=AGENT)
    assert [(each.prompt_ids, each.token_ids, each.token_logprobs) for each in rebuilt] == [
        (response.prompt_ids, response.token_ids, response.token_logprobs) for response in served
    ]


async def test_a_response_without_token_ids_logs_no_token_fields(tmp_path: Path) -> None:
    """Without the knob, an ``llm_response_received`` line holds none of the token id fields."""
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(text="I move left.", log_path=log_path, runs=[[None]])

    [line] = [line for line in log_path.read_text().splitlines() if "llm_response_received" in line]
    assert "token_ids" not in line
    assert "prompt_prefix_tokens" not in line
    assert "prompt_tail_ids" not in line
    assert "token_logprobs" not in line
    assert recorded_token_ids(events=await load_events(log_path=log_path), agent_id=AGENT) == []


async def test_a_restarted_runner_starts_again_from_an_empty_prefix(tmp_path: Path) -> None:
    """A resume or a swap starts a new runner, whose first prompt shares nothing with the log."""
    first = ServedResponse(
        prompt_ids=[1, 2], token_ids=[3], token_logprobs=logprobs_for(token_ids=[3])
    )
    second = ServedResponse(
        prompt_ids=[1, 2, 3, 4], token_ids=[5], token_logprobs=logprobs_for(token_ids=[5])
    )
    after_restart = ServedResponse(
        prompt_ids=[1, 2, 3, 4, 5, 6], token_ids=[7], token_logprobs=logprobs_for(token_ids=[7])
    )
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(
        text="I move left.", log_path=log_path, runs=[[first, second], [after_restart]]
    )

    events = await load_events(log_path=log_path)
    assert [each.token_ids_index for each in logged_responses(events=events)] == [0, 1, 0]
    rebuilt = recorded_token_ids(events=events, agent_id=AGENT)
    assert [each.prompt_ids for each in rebuilt] == [
        first.prompt_ids,
        second.prompt_ids,
        after_restart.prompt_ids,
    ]


def test_a_discarded_attempt_drops_its_token_ids() -> None:
    state = _StreamingState(token_id_log=TokenIdLog())
    state.mark_attempt_start()
    state.note_token_ids(
        details={PROMPT_TOKEN_IDS_DETAIL: [1], TOKEN_IDS_DETAIL: [2], TOKEN_LOGPROBS_DETAIL: [-0.5]}
    )

    state.discard_failed_attempt()

    assert state.response_token_ids is None


async def test_a_skipped_index_fails_instead_of_rebuilding_a_wrong_prompt(tmp_path: Path) -> None:
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(
        text="I move left.",
        log_path=log_path,
        runs=[
            [
                ServedResponse(
                    prompt_ids=[1], token_ids=[2], token_logprobs=logprobs_for(token_ids=[2])
                ),
                ServedResponse(
                    prompt_ids=[1, 2], token_ids=[3], token_logprobs=logprobs_for(token_ids=[3])
                ),
            ]
        ],
    )
    events = await load_events(log_path=log_path)
    second = logged_responses(events=events)[1]
    gapped: list[SimulationEvent] = []
    for event in events:
        if event is second:
            gapped.append(second.model_copy(update={"token_ids_index": 2}))
        else:
            gapped.append(event)

    with pytest.raises(TokenIdLogGap):
        recorded_token_ids(events=gapped, agent_id=AGENT)


async def test_only_the_named_agents_responses_are_read(tmp_path: Path) -> None:
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(
        text="I move left.",
        log_path=log_path,
        runs=[
            [
                ServedResponse(
                    prompt_ids=[1, 2], token_ids=[3], token_logprobs=logprobs_for(token_ids=[3])
                )
            ]
        ],
    )
    events = await load_events(log_path=log_path)

    assert recorded_token_ids(events=events, agent_id="player_b") == list[RecordedTokenIds]()
    assert len(recorded_token_ids(events=events, agent_id=AGENT)) == 1


async def test_an_empty_response_is_logged_when_it_carries_token_ids(tmp_path: Path) -> None:
    """The model wrote tokens, so the response is logged with its ids even without text."""
    served = ServedResponse(
        prompt_ids=[1, 2], token_ids=[3], token_logprobs=logprobs_for(token_ids=[3])
    )
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(text="", log_path=log_path, runs=[[served, None]])

    events = await load_events(log_path=log_path)
    [logged] = logged_responses(events=events)
    assert logged.text is None
    assert logged.token_ids == served.token_ids


async def test_a_log_written_before_logprobs_reads_back_without_them(tmp_path: Path) -> None:
    """A response logged with token ids and no ``token_logprobs`` reads back with None."""
    served = ServedResponse(prompt_ids=[1, 2], token_ids=[3], token_logprobs=[-0.5])
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(text="I move left.", log_path=log_path, runs=[[served]])
    events = await load_events(log_path=log_path)
    older: list[SimulationEvent] = []
    for event in events:
        if isinstance(event, LLMResponseReceived):
            older.append(event.model_copy(update={"token_logprobs": None}))
        else:
            older.append(event)

    [rebuilt] = recorded_token_ids(events=older, agent_id=AGENT)

    assert rebuilt.token_ids == [3]
    assert rebuilt.token_logprobs is None


async def test_an_event_with_more_logprobs_than_token_ids_fails_to_read(tmp_path: Path) -> None:
    served = ServedResponse(prompt_ids=[1, 2], token_ids=[3], token_logprobs=[-0.5])
    log_path = tmp_path / "signal_game.jsonl"
    await log_responses(text="I move left.", log_path=log_path, runs=[[served]])
    events = await load_events(log_path=log_path)
    edited: list[SimulationEvent] = []
    for event in events:
        if isinstance(event, LLMResponseReceived):
            edited.append(event.model_copy(update={"token_logprobs": [-0.5, -1.0]}))
        else:
            edited.append(event)

    with pytest.raises(TokenLogprobCountMismatch):
        recorded_token_ids(events=edited, agent_id=AGENT)
