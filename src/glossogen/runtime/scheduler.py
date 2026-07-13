"""Round-boundary scheduler that fires declared interventions when rounds advance.

Holds the schedule (list of ``ScheduledEvent``) bucketed by ``at_round``
and invokes the appropriate handler at each round boundary. The game
clock calls ``dispatch`` after emitting ``RoundAdvanced(R)`` and before
delivering the round's injections, so swaps see a clean state and the
new agent receives the round's injection just like any other.
"""

import logging
from typing import Any, Protocol

from glossogen.runtime.scheduled_events import ScheduledEvent, SetPostmortem, SwapAgent

logger = logging.getLogger(__name__)


class SchedulerOps(Protocol):
    """Hooks the scheduler invokes when a scheduled event fires.

    Decouples the scheduler from the supervisor — production code wires
    ``AutonomousSupervisor`` through this protocol so the scheduler does
    not need a concrete supervisor reference.
    """

    async def perform_agent_swap(self, spec: SwapAgent) -> None:
        """Swap the agent declared in ``spec`` for a fresh instance."""
        ...

    async def set_postmortem_enabled(self, round_number: int, enabled: bool) -> None:
        """Toggle postmortem at the given round boundary."""
        ...

    async def inject_case_payload(self, round_number: int, payload: dict[str, Any]) -> None:
        """Hand ``payload`` to the scenario to override the round's case."""
        ...


class RoundBoundaryScheduler:
    """Bucketed schedule of interventions, dispatched once per round boundary.

    ``events`` is the full list of ``ScheduledEvent`` declared in the
    scenario knobs / config. Each event is bucketed by ``at_round`` and
    fires when the game clock advances to that round. Each round's
    bucket fires at most once per simulation (``dispatch`` is idempotent
    on subsequent calls for the same round). Within a bucket, events
    fire in declared order — declare ``set_postmortem`` before
    ``swap_agent`` for the same round to ensure the new agent never
    sees postmortem state.
    """

    def __init__(
        self,
        events: list[ScheduledEvent],
        already_fired_rounds: frozenset[int],
    ) -> None:
        events_by_round: dict[int, list[ScheduledEvent]] = {}
        for event in events:
            events_by_round.setdefault(event.at_round, []).append(event)
        self._events_by_round = events_by_round
        self._fired_rounds: set[int] = set(already_fired_rounds)

    @property
    def empty(self) -> bool:
        """Return True when no scheduled events are configured."""
        return not self._events_by_round

    async def dispatch(
        self,
        round_number: int,
        ops: SchedulerOps,
    ) -> None:
        """Fire all events scheduled for ``round_number`` in declared order.

        Subsequent calls with the same ``round_number`` are no-ops.
        Handlers are awaited sequentially so that, for example, a
        postmortem-disable fires before a same-round swap and the new
        agent's reconstructed history reflects the disabled state.
        """
        if round_number in self._fired_rounds:
            return
        self._fired_rounds.add(round_number)
        events = self._events_by_round.get(round_number, [])
        if not events:
            return
        logger.info(
            "Dispatching %d scheduled event(s) at round %d",
            len(events),
            round_number,
        )
        for event in events:
            if isinstance(event, SwapAgent):
                await ops.perform_agent_swap(spec=event)
            elif isinstance(event, SetPostmortem):
                await ops.set_postmortem_enabled(
                    round_number=round_number,
                    enabled=event.enabled,
                )
            else:
                await ops.inject_case_payload(
                    round_number=round_number,
                    payload=event.payload,
                )
