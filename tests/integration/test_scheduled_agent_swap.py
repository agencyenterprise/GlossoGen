"""A scheduled mid-run agent swap, end to end.

This is the mechanism the protocol-learnability experiments rest on: replace one
agent at a round boundary, hand the replacement a windowed view of the channel,
and measure whether it can pick up the protocol its predecessor negotiated.

The failure mode is silent. If the window is computed wrongly the newcomer reads
the messages that defined the protocol, the run completes, the transcript looks
right, and the resulting number answers a different question than the one asked.
Nothing raises. So the assertions here are about what the swapped-in agent can
see, not about whether the swap ran.

The arithmetic behind each visibility kind is pinned in
`tests/unit/test_channel_router.py`. What these prove is that the swap reaches
it: the window arrives at the router, at the successor's `read_channel`, and at
the seed history it starts from.
"""

from pathlib import Path
from typing import Any, NamedTuple

import orjson
import pytest

from glossogen.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityNone,
    SwapAgent,
)
from tests.fakes.scripted_agent_model import SayTurn, ScriptedTurn, ToolTurn
from tests.testbed.simulation_harness import SimulationResult, never_times_out, run_simulation
from tests.testbed.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

# The harness routes each agent to its script by model name, so the swapped-in
# generation needs a name of its own to get a script of its own.
REPLACEMENT_SCRIPT_KEY = "first_agent_gen2"
REPLACEMENT_MODEL = f"scripted::{REPLACEMENT_SCRIPT_KEY}"
# One round for the predecessor to build history, the swap round, then one more
# so a full round runs with the successor in it. `at_round` cannot go below 2,
# so this is the shortest run that covers all three. Further rounds repeat the
# last one.
SWAP_ROUND = 2
ROUND_COUNT = 3
MESSAGES_PER_AGENT = 2


def send_turn(*, text: str) -> ToolTurn:
    """Send to the link channel, forcing past optimistic concurrency."""
    return ToolTurn(
        tool_name="send_message",
        args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
    )


def numbered_cycle(*, opening: list[ScriptedTurn], prefix: str, count: int) -> list[ScriptedTurn]:
    """Repeat a cycle `count` times, each sending a message you can identify.

    A cycle is one model call, not one round, and a scripted agent runs its
    cycles back to back: `read_notifications` only parks when nothing else was
    dispatched in the last `PARALLEL_DETECTION_WINDOW_SECONDS`, and a script has
    no thinking time between calls. So these messages land wherever the runtime
    happens to be, and no test here reads meaning into which round that was.
    The suffixes are for telling one message from another, nothing more.
    """
    turns: list[ScriptedTurn] = []
    for index in range(1, count + 1):
        turns.extend(opening)
        turns.append(send_turn(text=f"{prefix}-{index}"))
        turns.append(ToolTurn(tool_name="read_notifications", args={}))
        turns.append(SayTurn(text="idle"))
    return turns


def speak(*, prefix: str, count: int) -> list[ScriptedTurn]:
    """Send identifiable messages, one per cycle."""
    return numbered_cycle(opening=[], prefix=prefix, count=count)


def read_then_speak(*, prefix: str, count: int) -> list[ScriptedTurn]:
    """Read the channel before sending. The read is what the tests inspect."""
    opening: list[ScriptedTurn] = [
        ToolTurn(tool_name="read_channel", args={"channel_id": LINK_CHANNEL_ID, "last_n": 50})
    ]
    return numbered_cycle(opening=opening, prefix=prefix, count=count)


# An empty script drops the agent straight into the harness's idle cycle, where
# it polls and parks. The second agent stays quiet so every message on the
# channel comes from the agent being swapped, which is the one whose view the
# assertions are about.
STAYS_QUIET: list[ScriptedTurn] = []


def build_scenario(*, swap: SwapAgent) -> SmokeScenario:
    """Build the smoke scenario carrying one scheduled swap."""
    return SmokeScenario(
        knobs=SmokeKnobs(
            round_count=ROUND_COUNT,
            max_round_duration_seconds=45,
            model_overrides={},
            scheduled_events=[swap],
        )
    )


def index_of(*, events: list[dict[str, Any]], event_type: str, round_number: int | None) -> int:
    """Return the position of the first matching event in the log."""
    return next(
        index
        for index, event in enumerate(events)
        if event.get("event_type") == event_type
        and (round_number is None or event.get("round_number") == round_number)
    )


def texts_between(*, events: list[dict[str, Any]], start: int, end: int) -> list[str]:
    """Return the link-channel message texts logged in a slice of the log.

    Reading the window off the log's own ordering, rather than assuming one
    message per round, keeps the assertion exact however the agents interleave.
    """
    texts: list[str] = []
    for event in events[start:end]:
        if event.get("event_type") != "message_sent":
            continue
        message: dict[str, Any] | None = event.get("message")
        if message is not None and message.get("channel_id") == LINK_CHANNEL_ID:
            texts.append(str(message["text"]))
    return texts


def reads_after_the_swap(*, events: list[dict[str, Any]], agent_id: str) -> list[str]:
    """Return what `read_channel` returned to `agent_id` after it was swapped.

    Sliced at the swap event so these are the successor's reads and not its
    predecessor's. This is the successor's actual view of the channel: what came
    back over MCP, not what the runtime believed internally.
    """
    swap_index = next(
        index
        for index, event in enumerate(events)
        if event.get("event_type") == "agent_swapped_mid_run"
    )
    return [
        str(event.get("result", ""))
        for event in events[swap_index:]
        if event.get("event_type") == "tool_result_received"
        and event.get("tool_name") == "read_channel"
        and event.get("agent_id") == agent_id
    ]


class SwapRun(NamedTuple):
    """A finished swap run, reduced to the two surfaces the successor sees.

    `first_read` is what its first `read_channel` returned. `seed` is the
    reconstructed history it was handed, read back from the file the swap
    writes; the same list object goes into `initial_message_history`, so the
    file is the history and not a copy of it.

    `before_swap` is every link message logged before the swap event, taken
    from the log's own ordering. Both surfaces are checked against that same
    list, so neither test can hardcode a message that never got sent.
    """

    result: SimulationResult
    first_read: str
    seed: str
    before_swap: list[str]


async def run_swap(
    *,
    visibility: ChannelVisibilityNone | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SwapRun:
    """Run one swap and return what the successor could see afterwards.

    `visibility=None` leaves the channel at its default, which is full history.
    That is the control every hiding assertion below is measured against.
    """
    channel_visibility: dict[str, ChannelVisibility] = {}
    if visibility is not None:
        channel_visibility[LINK_CHANNEL_ID] = visibility

    result = await run_simulation(
        scenario=build_scenario(
            swap=SwapAgent(
                at_round=SWAP_ROUND,
                agent_id=FIRST_AGENT_ID,
                model=REPLACEMENT_MODEL,
                provider="anthropic",
                channel_visibility=channel_visibility,
            )
        ),
        scripts={
            FIRST_AGENT_ID: speak(prefix="gen1", count=MESSAGES_PER_AGENT),
            REPLACEMENT_SCRIPT_KEY: read_then_speak(prefix="gen2", count=MESSAGES_PER_AGENT),
            SECOND_AGENT_ID: STAYS_QUIET,
        },
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    reads = reads_after_the_swap(events=result.events, agent_id=FIRST_AGENT_ID)
    assert reads, "the successor never read the channel"

    swap_index = index_of(
        events=result.events, event_type="agent_swapped_mid_run", round_number=None
    )
    before_swap = texts_between(events=result.events, start=0, end=swap_index)
    assert before_swap, "nothing was sent before the swap, so nothing here proves anything"

    seed_file = tmp_path / f"resume_context_{FIRST_AGENT_ID}_round_{SWAP_ROUND}.json"
    # Round through orjson so the assertions read decoded text and not whatever
    # escaping the dump happened to use.
    seed = orjson.dumps(orjson.loads(seed_file.read_bytes())).decode()

    return SwapRun(result=result, first_read=reads[0], seed=seed, before_swap=before_swap)


async def test_a_default_swap_replaces_the_agent_and_withholds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A swap with no visibility set: it fires, the run continues, nothing is hidden.

    Also the control for the test below. Without it, a swap that broke
    `read_channel` outright, or handed the successor an empty history, would
    satisfy the hiding assertions exactly as well as one that windowed
    correctly. One simulation covers both, so it is one test.
    """
    run = await run_swap(visibility=None, tmp_path=tmp_path, monkeypatch=monkeypatch)
    result = run.result

    swapped = result.of_type(event_type="agent_swapped_mid_run")
    assert len(swapped) == 1
    assert swapped[0]["agent_id"] == FIRST_AGENT_ID
    assert swapped[0]["new_model"] == REPLACEMENT_MODEL
    assert swapped[0]["round_number"] == SWAP_ROUND

    # The successor ran under the same agent id, so the timeline is continuous.
    texts = [str(m["text"]) for m in result.messages_on(channel_id=LINK_CHANNEL_ID)]
    assert any(text.startswith("gen1-") for text in texts)
    assert any(text.startswith("gen2-") for text in texts)

    # Both routes into the successor stay open.
    for text in run.before_swap:
        assert text in run.first_read, f"{text} predates the swap and should still be readable"
        assert text in run.seed, f"{text} predates the swap and should still be in its history"

    assert result.failed_tool_calls() == []
    assert result.of_type(event_type="simulation_ended")


async def test_a_hidden_channel_reaches_the_successor_on_neither_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`none` closes both ways in: `read_channel` and the seed history.

    Closing one is not enough. Windowing the channel while leaving the
    predecessor's `read_channel` returns in the reconstructed history means the
    successor reads the withheld messages out of its own context instead of off
    the channel, and the window has bought nothing.

    The predecessor's messages stay in the channel and in the JSONL either way.
    What changes is only what this one agent is shown.
    """
    run = await run_swap(
        visibility=ChannelVisibilityNone(), tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    for text in run.before_swap:
        assert text not in run.first_read, f"{text} predates the swap and should be hidden"
        assert text not in run.seed, f"{text} predates the swap and should not be in its history"

    # The channel itself is untouched, so metrics and the viewer still see the
    # full transcript.
    logged = {str(m["text"]) for m in run.result.messages_on(channel_id=LINK_CHANNEL_ID)}
    assert set(run.before_swap) <= logged
