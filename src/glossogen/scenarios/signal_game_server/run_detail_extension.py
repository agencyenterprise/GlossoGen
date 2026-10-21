"""signal_game_server's extension to the run-detail API: the judge's reading of each round.

The judge is called at the end of a round that put something new on the server. Each
call is one ``signal_game_server_judged`` event, and the extras repackage it for the
round-detail panel: the texts the judge was shown, in the order it numbered them, each
marked flagged or passed with the judge's reason when flagged; the names it flagged
from the tree beyond those texts; and every tool call it made with its input and output.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.signal_game_server.events import (
    JudgeToolCall,
    SignalGameServerCheat,
    SignalGameServerJudged,
)
from glossogen.scenarios.signal_game_server.ids import WrittenTextKind


class SignalGameServerJudgedTextView(BaseModel):
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


class SignalGameServerJudgement(BaseModel):
    """One judge call: what it read, what it flagged, and what it ran.

    ``flagged_from_tree`` holds the names the judge flagged that were not among the
    numbered texts.
    """

    round_number: int
    texts: list[SignalGameServerJudgedTextView]
    flagged_from_tree: list[SignalGameServerCheat]
    tool_calls: list[JudgeToolCall]


class SignalGameServerRunExtras(ScenarioRunExtrasBase):
    """The judge's reading of every judged round, in round order."""

    scenario_name: Literal["signal_game_server"] = "signal_game_server"
    judgements: list[SignalGameServerJudgement]


def _judgement_of(event: SignalGameServerJudged) -> SignalGameServerJudgement:
    """Match each cheat to the text it names; the rest were flagged from the tree."""
    cheats_by_text = {(cheat.kind, cheat.path, cheat.author): cheat for cheat in event.cheats}
    texts: list[SignalGameServerJudgedTextView] = []
    matched: set[tuple[WrittenTextKind, str, str]] = set()
    for number, text in enumerate(event.texts, start=1):
        key = (text.kind, text.path, text.author)
        cheat = cheats_by_text.get(key)
        reason: str | None = None
        if cheat is not None:
            matched.add(key)
            reason = cheat.reason
        texts.append(
            SignalGameServerJudgedTextView(
                number=number,
                kind=text.kind,
                path=text.path,
                author=text.author,
                text=text.text,
                flagged=cheat is not None,
                reason=reason,
            )
        )
    return SignalGameServerJudgement(
        round_number=event.round_number,
        texts=texts,
        flagged_from_tree=[
            cheat for cheat in event.cheats if (cheat.kind, cheat.path, cheat.author) not in matched
        ],
        tool_calls=list(event.tool_calls),
    )


class SignalGameServerRunDetailExtension(ScenarioRunDetailExtension):
    """signal_game_server's hook into ``RunDetailResponse.scenario_extras``."""

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = SignalGameServerRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> SignalGameServerRunExtras:
        """One judgement per ``signal_game_server_judged`` event."""
        _ = agents_by_id, messages
        judged = sorted(
            (event for event in events if isinstance(event, SignalGameServerJudged)),
            key=lambda event: event.round_number,
        )
        return SignalGameServerRunExtras(
            judgements=[_judgement_of(event=event) for event in judged]
        )
