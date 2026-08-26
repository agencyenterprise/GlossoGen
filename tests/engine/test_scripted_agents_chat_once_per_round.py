"""The paced harness puts each agent's message in its own round, every time.

`run_rounds` gives every agent one send per round behind a `RoundGate`, and the
notebooks describe the result as one message per agent per round with a flat
characters-per-round plot. Before the gates existed, agents ran their cycles
back to back and spent a whole multi-round script inside round one, so the
notebooks' prose and their generated artifact disagreed (issue #132). These
tests pin the paced contract so that disagreement cannot come back silently.

What reproduces across runs is each sender's own stream, message text, channel
and round attribution. The interleaving of different senders within a round
stays the event loop's to choose, so nothing here compares global order; see
`tests/structural_equivalence.py`.
"""

from pathlib import Path

import pytest

from glossogen.testing import assert_agents_chatted_every_round, run_rounds
from tests.structural_equivalence import messages_by_sender

SCENARIO = "warehouse_robot_recovery"
PRESET = "knobs_default"
ROUNDS = 3

pytestmark = pytest.mark.xdist_group(SCENARIO)


async def test_every_agent_chats_exactly_once_in_every_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The docstring's "once per round" is paced, not merely budgeted."""
    result = await run_rounds(
        scenario_name=SCENARIO,
        preset_name=PRESET,
        round_count=ROUNDS,
        overrides={},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    assert_agents_chatted_every_round(result=result, round_count=ROUNDS)


async def test_two_runs_place_every_message_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each sender's stream, round attribution included, reproduces run to run."""
    first = await run_rounds(
        scenario_name=SCENARIO,
        preset_name=PRESET,
        round_count=ROUNDS,
        overrides={},
        tmp_path=tmp_path / "first",
        monkeypatch=monkeypatch,
    )
    second = await run_rounds(
        scenario_name=SCENARIO,
        preset_name=PRESET,
        round_count=ROUNDS,
        overrides={},
        tmp_path=tmp_path / "second",
        monkeypatch=monkeypatch,
    )

    assert messages_by_sender(first.events) == messages_by_sender(second.events)
