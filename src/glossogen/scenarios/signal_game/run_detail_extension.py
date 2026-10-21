"""signal_game's extension to the run-detail API: the plaintext judge's reading of each round.

Under the ``file_system`` medium the judge is called at the end of a round that put
something new on the server. Each call is one ``signal_game_plaintext_judged`` event,
and the extras repackage it for the round-detail panel: the texts the judge was shown,
in the order it numbered them, each marked flagged or passed with the judge's reason
when flagged; the names it flagged from the tree beyond those texts; and every tool
call it made with its input and output. A ``grid`` run has no judge and no judgements.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.signal_game.events import (
    JudgeToolCall,
    SignalGameCheat,
    SignalGamePlaintextJudged,
    SignalGameRoundStarted,
)
from glossogen.scenarios.signal_game.ids import Medium, WrittenTextKind


class SignalGameJudgedTextView(BaseModel):
    """One text the judge was shown, with its decision.

    ``number`` is the position the judge saw it under, from 1. ``reason`` is the
    judge's reason when it flagged the text, None when it passed it.
    """

    number: int
    kind: WrittenTextKind
    path: str
    author: str
    text: str
    flagged: bool
    reason: str | None


class SignalGameJudgement(BaseModel):
    """One judge call: what it read, what it flagged, and what it ran.

    ``texts`` is empty for a log that recorded only their count, which
    ``texts_judged`` always carries. ``flagged_from_tree`` holds the names the judge
    flagged that were not among the numbered texts.
    """

    round_number: int
    texts_judged: int
    texts: list[SignalGameJudgedTextView]
    flagged_from_tree: list[SignalGameCheat]
    tool_calls: list[JudgeToolCall]


class SignalGameRunExtras(ScenarioRunExtrasBase):
    """The run's medium and the judge's reading of every judged round, in round order."""

    scenario_name: Literal["signal_game"] = "signal_game"
    medium: Medium
    judgements: list[SignalGameJudgement]


def _medium_of(events: list[SimulationEvent]) -> Medium:
    """The medium the first round started under; ``grid`` for a run with no round."""
    for event in events:
        if isinstance(event, SignalGameRoundStarted):
            return event.medium
    return Medium.GRID


def _judgement_of(event: SignalGamePlaintextJudged) -> SignalGameJudgement:
    """Match each cheat to the text it names; the rest were flagged from the tree."""
    cheats_by_text = {(cheat.kind, cheat.path, cheat.author): cheat for cheat in event.cheats}
    texts: list[SignalGameJudgedTextView] = []
    matched: set[tuple[WrittenTextKind, str, str]] = set()
    for number, text in enumerate(event.texts, start=1):
        key = (text.kind, text.path, text.author)
        cheat = cheats_by_text.get(key)
        reason: str | None = None
        if cheat is not None:
            matched.add(key)
            reason = cheat.reason
        texts.append(
            SignalGameJudgedTextView(
                number=number,
                kind=text.kind,
                path=text.path,
                author=text.author,
                text=text.text,
                flagged=cheat is not None,
                reason=reason,
            )
        )
    return SignalGameJudgement(
        round_number=event.round_number,
        texts_judged=event.texts_judged,
        texts=texts,
        flagged_from_tree=[
            cheat for cheat in event.cheats if (cheat.kind, cheat.path, cheat.author) not in matched
        ],
        tool_calls=list(event.tool_calls),
    )


class SignalGameRunDetailExtension(ScenarioRunDetailExtension):
    """signal_game's hook into ``RunDetailResponse.scenario_extras``."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SignalGameRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> SignalGameRunExtras:
        """The medium and one judgement per ``signal_game_plaintext_judged`` event."""
        _ = agents_by_id, messages
        judged = sorted(
            (event for event in events if isinstance(event, SignalGamePlaintextJudged)),
            key=lambda event: event.round_number,
        )
        return SignalGameRunExtras(
            medium=_medium_of(events=events),
            judgements=[_judgement_of(event=event) for event in judged],
        )
