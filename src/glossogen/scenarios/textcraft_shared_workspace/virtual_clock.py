"""Virtual time that charges each model request what a hosted API would.

A local inference server shares one GPU across every agent, so a request's real
latency grows with how many teammates are generating at the same moment, and
the order in which agents act follows that contention. A hosted API does not
behave this way: each request costs roughly a fixed overhead plus its own
tokens, whatever other callers are doing. This clock simulates the API case on
any backend.

Each agent's request starts at a virtual instant and completes at::

    start + base_latency_s + output_tokens / output_tokens_per_second

computed from that request's own usage, so it is independent of server load.
The runner reports each response here before executing any of its tool calls
and waits to be released. The clock is a conservative discrete-event scheduler:
it releases the earliest pending response only once no agent could still act at
an earlier virtual instant. An agent whose request is still in flight
contributes a lower bound of ``start + minimum_latency_s``. Tool calls are
instantaneous in virtual time, and at most one released agent executes at a
time, so the environment sees effects in virtual order, not in the order the
GPU happened to finish them.

The scenario drives the clock through the platform's clock hooks, and it is the
time source for waits while it runs: a ``read_notifications(timeout_s=...)``
timeout counts virtual seconds. A parked agent is not a lower bound: it acts again only when an
action, a message or one of these timers wakes it, at the instant that did so.
Wall-clock limits still apply as a safety net and should be set generously.
"""

import asyncio
import heapq
import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


@dataclass(frozen=True)
class VirtualClockConfig:
    """The latency model the scenario simulates.

    Prompt processing is free, which is close to a hosted API with prompt caching.
    """

    base_latency_s: float
    output_tokens_per_second: float

    def __post_init__(self) -> None:
        """Reject a model that could make a request free or time run backwards."""
        if not math.isfinite(self.base_latency_s) or self.base_latency_s < 0:
            raise ValueError("base_latency_s must be finite and nonnegative")
        if not self.output_tokens_per_second > 0:
            raise ValueError("output_tokens_per_second must be positive")

    def latency_s(self, output_tokens: int) -> float:
        """Virtual duration of one request that generated ``output_tokens``."""
        return self.base_latency_s + max(0, output_tokens) / self.output_tokens_per_second

    @property
    def minimum_latency_s(self) -> float:
        """The least any request can take, including one that reports no usage."""
        return self.latency_s(output_tokens=0)


class _Phase(str, Enum):
    """Where an agent is, as far as virtual time is concerned."""

    INFERRING = "inferring"
    """A model request is in flight; its completion time is not known yet."""
    PENDING = "pending"
    """The response is back and its virtual completion time known; tools not run yet."""
    EXECUTING = "executing"
    """Released: its tools are running at the current instant."""
    PARKED = "parked"
    """Suspended on a wait; only a wake or a timer moves it."""
    RETIRED = "retired"
    """Its runner has returned."""


@dataclass
class _AgentState:
    """One agent's phase, when its request started, and the gate a pending response waits on."""

    phase: _Phase
    started_at: float
    ready_at: float
    gate: asyncio.Future[None] | None


class StepTiming(NamedTuple):
    """The virtual interval one released request occupied."""

    started_at: float
    completed_at: float


CancelTimer = Callable[[], None]


class VirtualClock:
    """Orders agents' model responses by simulated API latency."""

    def __init__(self, config: VirtualClockConfig, agent_ids: list[str]) -> None:
        self._config = config
        self._now = 0.0
        # Every runner starts by issuing a request at time zero.
        self._agents = {
            agent_id: _AgentState(phase=_Phase.INFERRING, started_at=0.0, ready_at=0.0, gate=None)
            for agent_id in agent_ids
        }
        self._timers: list[tuple[float, int, Callable[[], None]]] = []
        self._cancelled_timers: set[int] = set()
        self._timer_ids = itertools.count()
        self._round_started_at = 0.0
        self._stopped = False
        self._advancing = False
        self._advance_again = False

    @property
    def config(self) -> VirtualClockConfig:
        """The latency model in use."""
        return self._config

    def time(self) -> float:
        """The current virtual instant, in seconds since the run started."""
        return self._now

    def round_elapsed_s(self) -> float:
        """Virtual seconds since the current round started."""
        return self._now - self._round_started_at

    def start_round(self) -> None:
        """Start measuring ``round_elapsed_s`` from the current instant."""
        self._round_started_at = self._now

    def begin_inference(self, agent_id: str) -> None:
        """Record that ``agent_id`` is issuing a model request now.

        A request already in flight keeps its original start, so a retried
        request is charged from the first attempt.
        """
        state = self._agents[agent_id]
        if state.phase is _Phase.INFERRING or state.phase is _Phase.RETIRED:
            return
        state.phase = _Phase.INFERRING
        state.started_at = self._now
        self._advance()

    async def complete_inference(self, agent_id: str, output_tokens: int) -> StepTiming:
        """Report a finished response and wait until virtual time reaches its end."""
        state = self._agents[agent_id]
        started_at = self._now
        if state.phase is _Phase.INFERRING:
            started_at = state.started_at
        ready_at = started_at + self._config.latency_s(output_tokens=output_tokens)
        timing = StepTiming(started_at=started_at, completed_at=ready_at)
        if state.phase is _Phase.RETIRED:
            return timing
        if self._stopped:
            # Nothing is ordered any more; keep each agent's timeline consistent.
            self._now = max(self._now, ready_at)
            state.phase = _Phase.EXECUTING
            return timing
        gate: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        state.phase = _Phase.PENDING
        state.ready_at = ready_at
        state.gate = gate
        self._advance()
        await gate
        return timing

    def park(self, agent_id: str) -> None:
        """Record that ``agent_id`` suspended on a wait."""
        state = self._agents[agent_id]
        if state.phase is _Phase.RETIRED:
            return
        state.phase = _Phase.PARKED
        self._advance()

    def wake(self, agent_id: str) -> None:
        """Record that ``agent_id`` resumed now; its next request starts at this instant."""
        state = self._agents[agent_id]
        if state.phase is _Phase.RETIRED:
            return
        state.phase = _Phase.INFERRING
        state.started_at = self._now
        self._advance()

    async def occupy(self, agent_id: str, duration_s: float) -> None:
        """Keep the executing ``agent_id`` busy inside a tool call for ``duration_s``.

        The agent stops holding the execution slot, so teammates act meanwhile,
        and it is not a lower bound: only the timer that ends the interval moves
        it. When that timer fires the agent takes the slot back and its tool call
        resumes at ``now + duration_s``; its next request starts when the call
        returns. ``stop`` and ``retire`` end the interval early.
        """
        state = self._agents[agent_id]
        if duration_s <= 0 or self._stopped or state.phase is _Phase.RETIRED:
            return
        gate: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        state.phase = _Phase.PARKED
        state.ready_at = self._now + duration_s
        state.gate = gate

        def finish() -> None:
            if gate.done() or state.phase is _Phase.RETIRED:
                return
            state.phase = _Phase.EXECUTING
            gate.set_result(None)

        self.schedule_timer(duration_s, finish)
        await gate

    def retire(self, agent_id: str) -> None:
        """Remove ``agent_id`` from scheduling once its runner has returned."""
        state = self._agents.get(agent_id)
        if state is None:
            return
        state.phase = _Phase.RETIRED
        if state.gate is not None and not state.gate.done():
            state.gate.set_result(None)
        self._advance()

    def enlist(self, agent_id: str) -> None:
        """Schedule ``agent_id`` again once a new runner replaces its retired one.

        The new runner's first request starts at the current instant.
        """
        state = self._agents[agent_id]
        if state.phase is not _Phase.RETIRED:
            return
        state.phase = _Phase.INFERRING
        state.started_at = self._now
        state.gate = None
        self._advance()

    def stop(self) -> None:
        """Release every pending response at once; the run is over.

        Time moves to the latest released completion, so no agent's next
        request starts before its own previous one ended.
        """
        self._stopped = True
        for state in self._agents.values():
            if state.gate is not None and not state.gate.done():
                self._now = max(self._now, state.ready_at)
                state.phase = _Phase.EXECUTING
                state.gate.set_result(None)

    def schedule_timer(self, delay_seconds: float, callback: Callable[[], None]) -> CancelTimer:
        """Run ``callback`` once virtual time reaches ``now + delay_seconds``."""
        timer_id = next(self._timer_ids)
        heapq.heappush(self._timers, (self._now + max(0.0, delay_seconds), timer_id, callback))

        def cancel() -> None:
            self._cancelled_timers.add(timer_id)

        self._advance()
        return cancel

    def _next_timer(self) -> tuple[float, int, Callable[[], None]] | None:
        """The earliest timer that has not been cancelled."""
        while self._timers and self._timers[0][1] in self._cancelled_timers:
            _, timer_id, _ = heapq.heappop(self._timers)
            self._cancelled_timers.discard(timer_id)
        if not self._timers:
            return None
        return self._timers[0]

    def _advance(self) -> None:
        """Release the next event whose time has certainly come.

        Reentrant calls (a timer's callback waking an agent) only flag another
        pass, so the loop below sees one consistent state per step.
        """
        if self._advancing:
            self._advance_again = True
            return
        self._advancing = True
        try:
            self._advance_again = True
            while self._advance_again:
                self._advance_again = False
                self._step()
        finally:
            self._advancing = False

    def _step(self) -> None:
        """Process events until one agent is released or nothing more is certain."""
        while not self._stopped:
            states = self._agents.values()
            if any(state.phase is _Phase.EXECUTING for state in states):
                return
            bound = min(
                (
                    state.started_at + self._config.minimum_latency_s
                    for state in states
                    if state.phase is _Phase.INFERRING
                ),
                default=math.inf,
            )
            pending = min(
                (
                    (state.ready_at, agent_id)
                    for agent_id, state in self._agents.items()
                    if state.phase is _Phase.PENDING
                ),
                default=None,
            )
            timer = self._next_timer()
            event_at = math.inf
            if pending is not None:
                event_at = pending[0]
            if timer is not None:
                event_at = min(event_at, timer[0])
            if not math.isfinite(event_at) or event_at > bound:
                return
            self._now = max(self._now, event_at)
            if timer is not None and timer[0] <= event_at:
                heapq.heappop(self._timers)
                timer[2]()
                continue
            assert pending is not None
            released = self._agents[pending[1]]
            released.phase = _Phase.EXECUTING
            assert released.gate is not None
            released.gate.set_result(None)
            return
