"""The run every metric in this package is scored against.

One simulation serves the whole package. It is session-scoped rather than
per-file because there is a file per metric and running a simulation for each
would make adding a metric test cost a second of everyone's suite. The
`xdist_group` marker keeps these tests on one worker for the same reason:
without it each worker builds its own copy of the run.

Scoring every metric against one known transcript is also what makes the
numbers comparable. When `mean_chars_per_round` and `mean_chars_per_message`
disagree here, it is about the metrics, not about two different runs.
"""

import math

import pytest
import pytest_asyncio

from glossogen.runtime.scheduled_events import ScheduledEvent, SwapAgent
from tests.fakes.scripted_agent_model import SayTurn, ScriptedTurn, ToolTurn
from tests.testbed.metric_harness import MetricRun
from tests.testbed.simulation_harness import always_timed_out, never_times_out, run_simulation
from tests.testbed.smoke_scenario import (
    FIRST_AGENT_ID,
    LINK_CHANNEL_ID,
    SECOND_AGENT_ID,
    SmokeKnobs,
    SmokeScenario,
)

ROUND_COUNT = 2
SENDS_PER_AGENT = 2
FIRST_TEXT = "alpha"
SECOND_TEXT = "beta"

# What the run actually produces, which the per-metric expectations are
# arithmetic on. A scripted agent runs its cycles back to back and only parks
# once `PARALLEL_DETECTION_WINDOW_SECONDS` has passed with nothing else
# dispatched, so both agents spend their whole script inside round 1 even though
# two rounds run and both are judged. That is fine to score against, but it is
# stated here rather than assumed: `test_shared_run.py` fails first, and by
# name, if the runtime's pacing ever changes.
MESSAGES_TOTAL = SENDS_PER_AGENT * 2
ROUNDS_WITH_MESSAGES = 1
TOTAL_CHARS = SENDS_PER_AGENT * (len(FIRST_TEXT) + len(SECOND_TEXT))


def say_repeatedly(*, text: str, park_when_done: bool) -> list[ScriptedTurn]:
    """Send the same message on each cycle.

    `park_when_done` decides how a phase ends. Parking on
    `read_notifications` makes the agent idle, and the game clock checks idle
    before it checks the clock, so an idle agent always ends the phase early.
    An agent that never parks leaves only the wall-clock limit, which is the
    only way to produce a run whose phases end on timeout.
    """
    turns: list[ScriptedTurn] = []
    for _ in range(SENDS_PER_AGENT):
        turns.append(
            ToolTurn(
                tool_name="send_message",
                args={"channel_id": LINK_CHANNEL_ID, "text": text, "force": True},
            )
        )
        turns.append(SayTurn(text="sent"))
        if park_when_done:
            turns.append(ToolTurn(tool_name="read_notifications", args={}))
            turns.append(SayTurn(text="idle"))
    return turns


# Every test module here sets `pytestmark = METRIC_RUN_GROUP`, which pins them
# all to one xdist worker so they share the session-scoped run below. Spread
# across workers each would build its own, and the parallel suite would cost
# twelve simulations where the serial one costs a single simulation.
#
# It has to be a module-level mark rather than one added in
# `pytest_collection_modifyitems`: xdist reads the group during collection, and
# a mark applied from a conftest hook arrives after it has already scheduled.
# Measured, not assumed — the hook version ran twelve.
METRIC_RUN_GROUP = pytest.mark.xdist_group("metric-run")


async def build_metric_run(
    *,
    texts: dict[str, str],
    scheduled_events: list[ScheduledEvent],
    postmortem_seconds: float | None,
    round_seconds: float,
    park_when_done: bool,
    tmp_path_factory: pytest.TempPathFactory,
    dir_name: str,
) -> MetricRun:
    """Run the smoke scenario with each agent sending the text it is given.

    Parameterised because several metrics can only be checked against a corpus
    chosen for the purpose: a character-entropy oracle needs text whose
    distribution is known, and a compressibility test needs two corpora that
    differ only in how repetitive they are.
    """
    run_dir = tmp_path_factory.mktemp(dir_name)
    scenario = SmokeScenario(
        knobs=SmokeKnobs(
            round_count=ROUND_COUNT,
            max_round_duration_seconds=round_seconds,
            model_overrides={},
            scheduled_events=scheduled_events,
            postmortem_enabled=postmortem_seconds is not None,
            postmortem_duration_seconds=(
                postmortem_seconds if postmortem_seconds is not None else 120.0
            ),
        )
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-sent")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent")
        simulation = await run_simulation(
            scenario=scenario,
            scripts={
                agent_id: say_repeatedly(text=text, park_when_done=park_when_done)
                for agent_id, text in texts.items()
            },
            tmp_path=run_dir,
            monkeypatch=monkeypatch,
            # The two travel together: agents that park end a phase by going
            # idle, and agents that never park leave the timeout as the only
            # way a phase can end. Asking for a run whose phases time out is
            # therefore the same choice as scripting agents that never stop.
            phase_timed_out=never_times_out if park_when_done else always_timed_out,
        )
    return MetricRun(
        scenario=scenario,
        run_dir=run_dir,
        log_path=simulation.log_path,
        simulation=simulation,
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def metric_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """Run the smoke scenario once and hand every metric test the same result."""
    return await build_metric_run(
        texts={FIRST_AGENT_ID: FIRST_TEXT, SECOND_AGENT_ID: SECOND_TEXT},
        scheduled_events=[],
        postmortem_seconds=None,
        round_seconds=45.0,
        park_when_done=True,
        tmp_path_factory=tmp_path_factory,
        dir_name="metric-run",
    )


# Corpora with a character distribution the tests can do arithmetic on, all the
# same length. Length matters as much as content here: DEFLATE has a fixed
# header, so comparing a 4-byte message against a 5-byte one measures the
# overhead rather than the repetition. Sixteen bytes is long enough for the
# compressor to find the repeats.
CORPUS_LENGTH = 16
FLAT_TEXT = "a" * CORPUS_LENGTH  # one symbol   -> 0 bits/char
ALTERNATING_TEXT = "ab" * (CORPUS_LENGTH // 2)  # two symbols  -> 1 bit/char
DISTINCT_TEXT_A = "abcdefghijklmnop"  # 16 symbols   -> 4 bits/char
DISTINCT_TEXT_B = "qrstuvwxyz012345"  # 16 symbols   -> 4 bits/char

FLAT_ENTROPY_BITS = 0.0
ALTERNATING_ENTROPY_BITS = 1.0
DISTINCT_ENTROPY_BITS = math.log2(CORPUS_LENGTH)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def known_entropy_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """A repetitive run: every message is one or two distinct characters."""
    return await build_metric_run(
        texts={FIRST_AGENT_ID: FLAT_TEXT, SECOND_AGENT_ID: ALTERNATING_TEXT},
        scheduled_events=[],
        postmortem_seconds=None,
        round_seconds=45.0,
        park_when_done=True,
        tmp_path_factory=tmp_path_factory,
        dir_name="entropy-run",
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def high_entropy_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """The same message length with no repeated character at all."""
    return await build_metric_run(
        texts={FIRST_AGENT_ID: DISTINCT_TEXT_A, SECOND_AGENT_ID: DISTINCT_TEXT_B},
        scheduled_events=[],
        postmortem_seconds=None,
        round_seconds=45.0,
        park_when_done=True,
        tmp_path_factory=tmp_path_factory,
        dir_name="high-entropy-run",
    )


# A run where one agent is replaced partway through, which is the only shape
# the post-swap metrics can score. The successor needs its own script, so it
# needs its own model name: the harness routes scripts by the model the runner
# asks for.
SWAP_ROUND = 2
SUCCESSOR_KEY = "first_agent_successor"
SUCCESSOR_MODEL = f"scripted::{SUCCESSOR_KEY}"
SUCCESSOR_TEXT = "gamma"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def swapped_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """A run with a scheduled agent swap at `SWAP_ROUND`."""
    return await build_metric_run(
        texts={
            FIRST_AGENT_ID: FIRST_TEXT,
            SECOND_AGENT_ID: SECOND_TEXT,
            SUCCESSOR_KEY: SUCCESSOR_TEXT,
        },
        scheduled_events=[
            SwapAgent(
                at_round=SWAP_ROUND,
                agent_id=FIRST_AGENT_ID,
                model=SUCCESSOR_MODEL,
                provider="anthropic",
            )
        ],
        postmortem_seconds=None,
        round_seconds=45.0,
        park_when_done=True,
        tmp_path_factory=tmp_path_factory,
        dir_name="swapped-run",
    )


# Short phase limits, paired with agents that never park. Both endings are
# legitimate and the metrics exist to tell them apart, so a run that only ever
# ends on idle leaves the timeout half untested.
POSTMORTEM_TIMEOUT_SECONDS = 0.2
ROUND_TIMEOUT_SECONDS = 0.2


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def timed_out_postmortem_run(tmp_path_factory: pytest.TempPathFactory) -> MetricRun:
    """A run whose postmortem phases are cut off by the clock every round."""
    return await build_metric_run(
        texts={FIRST_AGENT_ID: FIRST_TEXT, SECOND_AGENT_ID: SECOND_TEXT},
        scheduled_events=[],
        postmortem_seconds=POSTMORTEM_TIMEOUT_SECONDS,
        round_seconds=ROUND_TIMEOUT_SECONDS,
        park_when_done=False,
        tmp_path_factory=tmp_path_factory,
        dir_name="postmortem-run",
    )
