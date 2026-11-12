"""Each operator's time on move_a_box's virtual clock, round by round, for the run-detail panel.

Rebuilt from the events a clock run logs. Each released model request is a
stretch of thinking. Each action takes the ``step_duration_s`` before it landed.
Each ``read_notifications`` wait lasts the virtual seconds it was parked for, and
ends for the reason the wait logged. Times are seconds since the round started,
the figure the depot readout shows.

The lanes stop where the last round ends. After that the run stops the clock,
which then no longer orders the agents' requests.
"""

from enum import Enum
from typing import NamedTuple

from pydantic import BaseModel

from glossogen.models.event import (
    AgentResumed,
    RoundEnded,
    SimulationEvent,
    SimulationStarted,
    WaitRegistered,
)
from glossogen.scenario_contract.parked_wait import WakeReason
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxOperatorFinished,
    MoveABoxRequestReleased,
    MoveABoxRoundStarted,
)

SAME_INSTANT_S = 1e-6
"""Two virtual times closer than this are one instant."""


class MoveABoxWakeCause(str, Enum):
    """Why a wait ended.

    ``other_acted``: another operator's action or finish landed at that instant.
    ``released``: the scenario let the operator go for another reason, such as a
    readout that had already changed or a new target. ``timer``: the timeout the
    operator set ran out. ``next_round``: the next round's briefing arrived.
    ``briefing``: a notification arrived. ``message``: a channel message arrived;
    a move_a_box run has no channel. ``run_ended``: the last round ended during
    the wait. ``still_waiting``: the log ends before the wait does.
    """

    OTHER_ACTED = "other_acted"
    RELEASED = "released"
    TIMER = "timer"
    NEXT_ROUND = "next_round"
    BRIEFING = "briefing"
    MESSAGE = "message"
    RUN_ENDED = "run_ended"
    STILL_WAITING = "still_waiting"


WAKE_CAUSES: tuple[tuple[str, MoveABoxWakeCause], ...] = (
    (WakeReason.NEXT_ROUND.value, MoveABoxWakeCause.NEXT_ROUND),
    (WakeReason.RELEASED.value, MoveABoxWakeCause.RELEASED),
    (WakeReason.TIMEOUT.value, MoveABoxWakeCause.TIMER),
    (WakeReason.NEW_MESSAGE.value, MoveABoxWakeCause.MESSAGE),
    (WakeReason.NEW_NOTIFICATION.value, MoveABoxWakeCause.BRIEFING),
    (WakeReason.DONE.value, MoveABoxWakeCause.RUN_ENDED),
)
"""Each wake reason's cause, in the order one is picked when a wake carries several."""


class MoveABoxThinkingSpan(BaseModel):
    """One model request, from when it started to when the clock released its response.

    ``cost_s`` is the request's whole virtual cost. A request issued before the
    round started has ``start_s`` cut to the round's start, so ``cost_s`` can be
    longer than the span.
    """

    start_s: float
    end_s: float
    cost_s: float
    output_tokens: int


class MoveABoxActionSpan(BaseModel):
    """One action, from when the operator started on it to when it landed.

    Each action takes ``step_duration_s``. With no step time the span starts
    where it ends.
    """

    start_s: float
    end_s: float
    sequence: int
    action: str
    direction: str | None
    reasoning: str | None


class MoveABoxFinishMark(BaseModel):
    """An operator finishing a crate. A finish takes no time.

    ``bay`` is the bay its operator was assigned that the crate was left on, or
    None when the crate stands on no such bay.
    """

    at_s: float
    crate_marking: str
    bay: int | None
    reasoning: str | None


class MoveABoxWaitSpan(BaseModel):
    """One ``read_notifications`` wait and why it ended.

    ``timeout_s`` is the timer the operator set, or None. ``woken_by`` is the
    operator whose action ended the wait when ``cause`` is ``other_acted``.
    """

    start_s: float
    end_s: float
    timeout_s: float | None
    cause: MoveABoxWakeCause
    woken_by: str | None


class MoveABoxClockLane(BaseModel):
    """Everything one operator did on the clock in one round."""

    agent_id: str
    thinking: list[MoveABoxThinkingSpan]
    actions: list[MoveABoxActionSpan]
    finishes: list[MoveABoxFinishMark]
    waits: list[MoveABoxWaitSpan]


class MoveABoxRoundClock(BaseModel):
    """One round on the virtual clock: how long it ran and one lane per operator."""

    duration_s: float
    step_duration_s: float
    lanes: list[MoveABoxClockLane]


class _InPlay(NamedTuple):
    """The events up to the end of the last round, and whether that round has ended."""

    events: list[SimulationEvent]
    run_over: bool


class ClockSettings(NamedTuple):
    """Whether a run played on the clock, and how long each action took."""

    virtual_clock: bool
    step_duration_s: float


class _Placed(NamedTuple):
    """A span in run time, with the operator and round its event logged.

    ``round_number`` is the round the request was released in, the action or
    finish landed in, or the wait started in.
    """

    agent_id: str
    round_number: int
    start_s: float
    end_s: float


class _PlacedThinking(NamedTuple):
    placed: _Placed
    span: MoveABoxThinkingSpan


class _PlacedAction(NamedTuple):
    placed: _Placed
    span: MoveABoxActionSpan


class _PlacedFinish(NamedTuple):
    placed: _Placed
    mark: MoveABoxFinishMark


class _PlacedWait(NamedTuple):
    """A wait in run time with the reasons it resumed, before its cause is settled."""

    placed: _Placed
    timeout_s: float | None
    reasons: tuple[str, ...]


class _SettledWait(NamedTuple):
    """A wait in run time and the span it draws, its cause settled."""

    placed: _Placed
    span: MoveABoxWaitSpan


class _Clip(NamedTuple):
    """A span's start and end in seconds since its round started."""

    start_s: float
    end_s: float


class _OpenWait(NamedTuple):
    """A wait that has started and not yet resumed."""

    round_number: int
    start_s: float
    timeout_s: float | None


class _Window(NamedTuple):
    """A round's stretch of virtual time, in seconds since the run started."""

    start_s: float
    end_s: float


class _TimelineBuilder:
    """Places every request, action, finish and wait of a run in run time, in log order.

    A wait starts where its operator's last request or landing left it, because
    a tool call takes no virtual time unless its actions do.
    """

    def __init__(self, agent_ids: list[str], step_duration_s: float) -> None:
        self.agent_ids = agent_ids
        self.step_duration_s = step_duration_s
        self.cursor = dict.fromkeys(agent_ids, 0.0)
        self.open_waits: dict[str, _OpenWait] = {}
        self.round_starts: dict[int, float] = {}
        self.thinking: list[_PlacedThinking] = []
        self.actions: list[_PlacedAction] = []
        self.finishes: list[_PlacedFinish] = []
        self.waits: list[_PlacedWait] = []
        self.latest_s = 0.0

    def add(self, event: SimulationEvent) -> None:
        """Place one event, if it is one the lanes draw."""
        if isinstance(event, MoveABoxRoundStarted) and event.virtual_time_s is not None:
            self.round_starts[event.round_number] = event.virtual_time_s
            self._reach(time_s=event.virtual_time_s)
        elif isinstance(event, MoveABoxRequestReleased) and event.agent_id in self.cursor:
            self._add_thinking(event=event)
        elif isinstance(event, MoveABoxActionTaken) and event.agent_id in self.cursor:
            self._add_action(event=event)
        elif isinstance(event, MoveABoxOperatorFinished) and event.agent_id in self.cursor:
            self._add_finish(event=event)
        elif isinstance(event, WaitRegistered) and event.agent_id in self.cursor:
            self.open_waits[event.agent_id] = _OpenWait(
                round_number=event.round_number,
                start_s=self.cursor[event.agent_id],
                timeout_s=event.deadline_s,
            )
        elif isinstance(event, AgentResumed) and event.agent_id in self.open_waits:
            self._close_wait(event=event)

    def close_open_waits(self, run_over: bool) -> None:
        """End every wait still open at the last instant placed.

        Once the last round has ended such a wait ends with the run. Otherwise
        the log stops before the wait does.
        """
        reasons: tuple[str, ...] = ()
        if run_over:
            reasons = (WakeReason.DONE.value,)
        for agent_id, opened in self.open_waits.items():
            self.waits.append(
                _PlacedWait(
                    placed=_Placed(
                        agent_id=agent_id,
                        round_number=opened.round_number,
                        start_s=opened.start_s,
                        end_s=max(self.latest_s, opened.start_s),
                    ),
                    timeout_s=opened.timeout_s,
                    reasons=reasons,
                )
            )
        self.open_waits = {}

    def _reach(self, time_s: float) -> None:
        self.latest_s = max(self.latest_s, time_s)

    def _move(self, agent_id: str, time_s: float) -> None:
        self.cursor[agent_id] = time_s
        self._reach(time_s=time_s)

    def _add_thinking(self, event: MoveABoxRequestReleased) -> None:
        self.thinking.append(
            _PlacedThinking(
                placed=_Placed(
                    agent_id=event.agent_id,
                    round_number=event.round_number,
                    start_s=event.started_at_s,
                    end_s=event.completed_at_s,
                ),
                span=MoveABoxThinkingSpan(
                    start_s=event.started_at_s,
                    end_s=event.completed_at_s,
                    cost_s=event.completed_at_s - event.started_at_s,
                    output_tokens=event.output_tokens,
                ),
            )
        )
        self._move(agent_id=event.agent_id, time_s=event.completed_at_s)

    def _add_action(self, event: MoveABoxActionTaken) -> None:
        landed = event.virtual_time_s
        if landed is None:
            return
        started = landed - self.step_duration_s
        self.actions.append(
            _PlacedAction(
                placed=_Placed(
                    agent_id=event.agent_id,
                    round_number=event.round_number,
                    start_s=started,
                    end_s=landed,
                ),
                span=MoveABoxActionSpan(
                    start_s=started,
                    end_s=landed,
                    sequence=event.sequence,
                    action=event.action,
                    direction=event.direction,
                    reasoning=event.reasoning,
                ),
            )
        )
        self._move(agent_id=event.agent_id, time_s=landed)

    def _add_finish(self, event: MoveABoxOperatorFinished) -> None:
        at_s = event.virtual_time_s
        if at_s is None:
            return
        self.finishes.append(
            _PlacedFinish(
                placed=_Placed(
                    agent_id=event.agent_id,
                    round_number=event.round_number,
                    start_s=at_s,
                    end_s=at_s,
                ),
                mark=MoveABoxFinishMark(
                    at_s=at_s,
                    crate_marking=event.crate_marking,
                    bay=event.bay,
                    reasoning=event.reasoning,
                ),
            )
        )
        self._move(agent_id=event.agent_id, time_s=at_s)

    def _close_wait(self, event: AgentResumed) -> None:
        opened = self.open_waits.pop(event.agent_id)
        end_s = opened.start_s + event.waited_seconds
        self.waits.append(
            _PlacedWait(
                placed=_Placed(
                    agent_id=event.agent_id,
                    round_number=opened.round_number,
                    start_s=opened.start_s,
                    end_s=end_s,
                ),
                timeout_s=opened.timeout_s,
                reasons=tuple(event.wake_reasons),
            )
        )
        self._move(agent_id=event.agent_id, time_s=end_s)


def clock_settings(events: list[SimulationEvent]) -> ClockSettings:
    """The run's ``virtual_clock`` and ``step_duration_s``.

    A run recorded before these knobs existed had no clock.
    """
    for event in events:
        if isinstance(event, SimulationStarted):
            config = event.scenario_config
            return ClockSettings(
                virtual_clock=bool(config.get("virtual_clock", False)),
                step_duration_s=float(config.get("step_duration_s", 0.0)),
            )
    return ClockSettings(virtual_clock=False, step_duration_s=0.0)


def _in_play(events: list[SimulationEvent]) -> _InPlay:
    """The events up to and including the end of the last round started."""
    started = [event.round_number for event in events if isinstance(event, MoveABoxRoundStarted)]
    if not started:
        return _InPlay(events=events, run_over=False)
    last_round = max(started)
    for index, event in enumerate(events):
        if isinstance(event, RoundEnded) and event.round_number == last_round:
            return _InPlay(events=events[: index + 1], run_over=True)
    return _InPlay(events=events, run_over=False)


def _cause_of(reasons: tuple[str, ...]) -> MoveABoxWakeCause:
    for reason, cause in WAKE_CAUSES:
        if reason in reasons:
            return cause
    return MoveABoxWakeCause.STILL_WAITING


def _landed_at(timeline: _TimelineBuilder, agent_id: str, time_s: float) -> bool:
    """Whether one of ``agent_id``'s actions or finishes landed at ``time_s``."""
    landings = [entry.placed for entry in timeline.actions] + [
        entry.placed for entry in timeline.finishes
    ]
    return any(
        placed.agent_id == agent_id and abs(placed.end_s - time_s) < SAME_INSTANT_S
        for placed in landings
    )


def _wait_span(wait: _PlacedWait, timeline: _TimelineBuilder) -> MoveABoxWaitSpan:
    """A wait with its cause.

    A release at the instant another operator's action or finish landed is
    that operator's doing.
    """
    placed = wait.placed
    cause = _cause_of(reasons=wait.reasons)
    woken_by: str | None = None
    if cause is MoveABoxWakeCause.RELEASED and placed.end_s > placed.start_s:
        for other in timeline.agent_ids:
            if other != placed.agent_id and _landed_at(
                timeline=timeline, agent_id=other, time_s=placed.end_s
            ):
                cause = MoveABoxWakeCause.OTHER_ACTED
                woken_by = other
                break
    return MoveABoxWaitSpan(
        start_s=placed.start_s,
        end_s=placed.end_s,
        timeout_s=wait.timeout_s,
        cause=cause,
        woken_by=woken_by,
    )


def _windows(timeline: _TimelineBuilder) -> dict[int, _Window]:
    """Each round runs from its start to the next round's start; the last one to the log's end."""
    ordered = sorted(timeline.round_starts.items())
    windows: dict[int, _Window] = {}
    for index, (round_number, start_s) in enumerate(ordered):
        end_s = timeline.latest_s
        if index + 1 < len(ordered):
            end_s = ordered[index + 1][1]
        windows[round_number] = _Window(start_s=start_s, end_s=max(end_s, start_s))
    return windows


def _shows_in(placed: _Placed, round_number: int, window: _Window) -> bool:
    """A span shows in the round its event logged, and in any other round it runs through."""
    if placed.round_number == round_number:
        return True
    return (
        placed.start_s < window.end_s - SAME_INSTANT_S
        and placed.end_s > window.start_s + SAME_INSTANT_S
    )


def _clipped(placed: _Placed, window: _Window) -> _Clip:
    """A span's start and end in seconds since the round started, cut to the round."""
    start_s = max(placed.start_s, window.start_s) - window.start_s
    end_s = min(placed.end_s, window.end_s) - window.start_s
    return _Clip(start_s=start_s, end_s=max(end_s, start_s))


def _retimed[Span: (MoveABoxThinkingSpan, MoveABoxActionSpan, MoveABoxWaitSpan)](
    span: Span, placed: _Placed, window: _Window
) -> Span:
    """``span`` timed from its round's start and cut to the round."""
    clip = _clipped(placed=placed, window=window)
    return span.model_copy(update={"start_s": clip.start_s, "end_s": clip.end_s})


def _lane(
    agent_id: str,
    timeline: _TimelineBuilder,
    waits: list[_SettledWait],
    round_number: int,
    window: _Window,
) -> MoveABoxClockLane:
    """One operator's spans in one round, timed from the round's start."""

    def mine(placed: _Placed) -> bool:
        return placed.agent_id == agent_id and _shows_in(
            placed=placed, round_number=round_number, window=window
        )

    return MoveABoxClockLane(
        agent_id=agent_id,
        thinking=[
            _retimed(span=entry.span, placed=entry.placed, window=window)
            for entry in timeline.thinking
            if mine(placed=entry.placed)
        ],
        actions=[
            _retimed(span=entry.span, placed=entry.placed, window=window)
            for entry in timeline.actions
            if mine(placed=entry.placed)
        ],
        finishes=[
            entry.mark.model_copy(
                update={"at_s": _clipped(placed=entry.placed, window=window).start_s}
            )
            for entry in timeline.finishes
            if mine(placed=entry.placed)
        ],
        waits=[
            _retimed(span=wait.span, placed=wait.placed, window=window)
            for wait in waits
            if mine(placed=wait.placed)
        ],
    )


def round_clocks(
    events: list[SimulationEvent], agent_ids: list[str]
) -> dict[int, MoveABoxRoundClock]:
    """Every started round's lanes, by round number; empty for a run with the clock off."""
    settings = clock_settings(events=events)
    if not settings.virtual_clock:
        return {}
    in_play = _in_play(events=events)
    timeline = _TimelineBuilder(agent_ids=agent_ids, step_duration_s=settings.step_duration_s)
    for event in in_play.events:
        timeline.add(event=event)
    timeline.close_open_waits(run_over=in_play.run_over)
    waits = [
        _SettledWait(placed=wait.placed, span=_wait_span(wait=wait, timeline=timeline))
        for wait in timeline.waits
    ]
    return {
        round_number: MoveABoxRoundClock(
            duration_s=window.end_s - window.start_s,
            step_duration_s=settings.step_duration_s,
            lanes=[
                _lane(
                    agent_id=agent_id,
                    timeline=timeline,
                    waits=waits,
                    round_number=round_number,
                    window=window,
                )
                for agent_id in agent_ids
            ],
        )
        for round_number, window in _windows(timeline=timeline).items()
    }
