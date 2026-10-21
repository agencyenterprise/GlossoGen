"""The run-detail extras carry the plaintext judge's reading of each judged round.

One scripted ``file_system`` round is played with the judge stubbed to flag the
content of ``/tmp/x`` after one shell call, and the extras are checked against it: the
texts in the judge's numbering with their decisions, a name flagged from the tree,
and the tool call. A cheat on a name that was not numbered, and a log that recorded
only the count of texts, are checked on constructed events. A ``grid`` round has no
judgement.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.signal_game.events import (
    SignalGameCheat,
    SignalGameJudgedText,
    SignalGamePlaintextJudged,
)
from glossogen.scenarios.signal_game.ids import (
    PLAYER_A,
    PLAYER_B,
    JudgeTool,
    Medium,
    WrittenTextKind,
)
from glossogen.scenarios.signal_game.plaintext_judge import (
    PlaintextVerdict,
    TextVerdict,
    TreeFinding,
)
from glossogen.scenarios.signal_game.run_detail_extension import (
    SignalGameRunDetailExtension,
    SignalGameRunExtras,
)
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from tests.scenarios.signal_game.judge_stub import stub_the_plaintext_judge
from tests.scenarios.signal_game.signal_game_play import (
    ONE_ROUND,
    build,
    end_round,
    end_round_on,
    play,
    read,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("signal_game")

FILE_SYSTEM = "knobs_file_system"


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
    scenario = build(preset_name=FILE_SYSTEM, overrides=ONE_ROUND)
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

    extras = SignalGameRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )
    assert isinstance(extras, SignalGameRunExtras)
    assert extras.medium is Medium.FILE_SYSTEM
    [judgement] = extras.judgements
    assert judgement.round_number == 1
    assert judgement.texts_judged == 3
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
    flagged_earlier_name = SignalGameCheat(
        kind=WrittenTextKind.NAME,
        path="/tmp/r",
        author=PLAYER_A,
        reason="r and e spell the start of red.",
    )
    event = SignalGamePlaintextJudged(
        round_number=2,
        texts_judged=1,
        cheats=[flagged_earlier_name],
        tool_calls=[],
        texts=[
            SignalGameJudgedText(
                kind=WrittenTextKind.NAME, path="/tmp/e", author=PLAYER_A, text="e"
            )
        ],
    )

    extras = SignalGameRunDetailExtension().build_extras(
        events=[event], agents_by_id={}, messages=[]
    )

    assert isinstance(extras, SignalGameRunExtras)
    [judgement] = extras.judgements
    assert [(text.path, text.flagged) for text in judgement.texts] == [("/tmp/e", False)]
    assert judgement.flagged_from_tree == [flagged_earlier_name]


def test_a_log_recording_only_the_count_shows_no_texts() -> None:
    event = SignalGamePlaintextJudged(round_number=1, texts_judged=12, cheats=[])

    extras = SignalGameRunDetailExtension().build_extras(
        events=[event], agents_by_id={}, messages=[]
    )

    assert isinstance(extras, SignalGameRunExtras)
    [judgement] = extras.judgements
    assert (judgement.texts_judged, judgement.texts, judgement.tool_calls) == (12, [], [])


async def test_a_grid_round_has_no_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        PLAYER_A: [read(), end_round(), wait_for_next_round()],
        PLAYER_B: [read(), end_round(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    extras = SignalGameRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )
    assert isinstance(extras, SignalGameRunExtras)
    assert extras.medium is Medium.GRID
    assert extras.judgements == []
