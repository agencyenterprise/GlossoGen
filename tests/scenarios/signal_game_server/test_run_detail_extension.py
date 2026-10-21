"""The run-detail extras carry the plaintext judge's reading of each judged round.

One scripted round is played with the judge stubbed to flag the content of ``/tmp/x``
after one shell call, and the extras are checked against it: the texts in the judge's
numbering with their decisions, a name flagged from the tree, and the tool call. A
cheat on a name that was not numbered is checked on a constructed event. A round that
put nothing on the server has no judgement.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.signal_game.ids import PLAYER_A, PLAYER_B
from glossogen.scenarios.signal_game_server.events import (
    SignalGameServerCheat,
    SignalGameServerJudged,
    SignalGameServerJudgedText,
)
from glossogen.scenarios.signal_game_server.ids import JudgeTool, WrittenTextKind
from glossogen.scenarios.signal_game_server.plaintext_judge import (
    PlaintextVerdict,
    TextVerdict,
    TreeFinding,
)
from glossogen.scenarios.signal_game_server.run_detail_extension import (
    SignalGameServerRunDetailExtension,
    SignalGameServerRunExtras,
)
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from tests.scenarios.signal_game_server.judge_stub import stub_the_plaintext_judge
from tests.scenarios.signal_game_server.signal_game_server_play import (
    ONE_ROUND,
    build,
    end_round_on,
    play,
    read,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("signal_game_server")


async def test_a_judged_round_shows_what_the_judge_read_ran_and_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_the_plaintext_judge(
        monkeypatch=monkeypatch,
        verdict=PlaintextVerdict(
            verdicts=[
                TextVerdict(number=1, reason="d is a single letter.", coordination=False),
                TextVerdict(number=2, reason="x is a single letter.", coordination=False),
                TextVerdict(
                    number=3, reason='"red" tells the partner the colour.', coordination=True
                ),
            ],
            tree_findings=[TreeFinding(reason="d completes a word with x.", path="/tmp/d")],
        ),
        tool_turns=[ToolTurn(tool_name="run_command", args={"command": "cat /tmp/x"})],
    )
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [
            read(),
            ToolTurn(
                tool_name="run_command", args={"command": "printf red > /tmp/x; mkdir /tmp/d"}
            ),
            end_round_on(row=1, col=1),
            wait_for_next_round(),
        ],
        PLAYER_B: [read(), end_round_on(row=2, col=1), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    extras = SignalGameServerRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )
    assert isinstance(extras, SignalGameServerRunExtras)
    [judgement] = extras.judgements
    assert judgement.round_number == 1
    assert [
        (text.number, text.kind, text.path, text.text, text.flagged, text.reason)
        for text in judgement.texts
    ] == [
        (1, WrittenTextKind.NAME, "/tmp/d", "d", True, "d completes a word with x."),
        (2, WrittenTextKind.NAME, "/tmp/x", "x", False, None),
        (3, WrittenTextKind.CONTENT, "/tmp/x", "red", True, '"red" tells the partner the colour.'),
    ]
    assert judgement.flagged_from_tree == []
    assert [(call.tool, call.input, call.output) for call in judgement.tool_calls] == [
        (JudgeTool.SHELL, "cat /tmp/x", "red")
    ]


def test_a_name_flagged_from_the_tree_alone_is_listed_apart() -> None:
    """A name passed in an earlier round is not numbered again, so a cheat on it has no
    text to attach to and lands in ``flagged_from_tree``."""
    flagged_earlier_name = SignalGameServerCheat(
        kind=WrittenTextKind.NAME,
        path="/tmp/r",
        author=PLAYER_A,
        reason="r and e spell the start of red.",
    )
    event = SignalGameServerJudged(
        round_number=2,
        texts=[
            SignalGameServerJudgedText(
                kind=WrittenTextKind.NAME, path="/tmp/e", author=PLAYER_A, text="e"
            )
        ],
        tool_calls=[],
        cheats=[flagged_earlier_name],
    )

    extras = SignalGameServerRunDetailExtension().build_extras(
        events=[event], agents_by_id={}, messages=[]
    )

    assert isinstance(extras, SignalGameServerRunExtras)
    [judgement] = extras.judgements
    assert [(text.path, text.flagged) for text in judgement.texts] == [("/tmp/e", False)]
    assert judgement.flagged_from_tree == [flagged_earlier_name]


async def test_a_round_that_wrote_nothing_has_no_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = stub_the_plaintext_judge(
        monkeypatch=monkeypatch, verdict=PlaintextVerdict(verdicts=[]), tool_turns=[]
    )
    scenario = build(overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round_on(row=1, col=1), wait_for_next_round()],
        PLAYER_B: [read(), end_round_on(row=2, col=1), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    extras = SignalGameServerRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )
    assert isinstance(extras, SignalGameServerRunExtras)
    assert extras.judgements == []
    assert stub.calls == []
