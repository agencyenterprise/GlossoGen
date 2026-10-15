"""``excess_moves``: the moves each player made beyond the shortest path to its final square.

Deterministic, read from signal_game's own events. A player that walks straight
to the square it finishes on makes no excess moves. Every detour or
back-and-forth counts (and a stay, in runs from before ``stay`` was removed), so
this is the costly behaviour that has no use for reaching the square, which is
what the paper's participants used to show that a movement was a signal. It is
the inefficiency measure of de Bie et al. (2010): moves used minus the minimal
number of moves required to reach the end square.

The metric does not say whether the excess was meant as a signal. A player
wandering because it is unsure also scores. Read it beside ``round_success`` and
the move traces in each round's note.
"""

import logging
from pathlib import Path
from statistics import fmean

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.signal_game.board import Square, path_length
from glossogen.scenarios.signal_game.events import (
    SignalGameMoveMade,
    SignalGameRoundResolved,
    SignalGameRoundStarted,
)

logger = logging.getLogger(__name__)


def excess_moves_by_agent(
    started: SignalGameRoundStarted, resolved: SignalGameRoundResolved
) -> dict[str, int]:
    """Each player's moves in the round minus the shortest path to where it finished."""
    excess: dict[str, int] = {}
    for agent_id, square in sorted(resolved.final_squares.items()):
        start = started.start_squares[agent_id]
        excess[agent_id] = resolved.moves_used[agent_id] - path_length(
            start=Square(row=start[0], col=start[1]), end=Square(row=square[0], col=square[1])
        )
    return excess


class ExcessMovesMetric(Metric):
    """Per round and player, moves beyond the shortest path to the final square."""

    name = "excess_moves"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over every resolved signal_game round, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        started = {
            event.round_number: event
            for event in events
            if isinstance(event, SignalGameRoundStarted)
        }
        resolved = [
            event
            for event in events
            if isinstance(event, SignalGameRoundResolved) and event.round_number in started
        ]
        if not resolved:
            logger.info("excess_moves: no resolved signal_game rounds in this run; skipping")
            return []
        traces: dict[tuple[int, str], list[str]] = {}
        for event in events:
            if isinstance(event, SignalGameMoveMade):
                traces.setdefault((event.round_number, event.agent_id), []).append(event.direction)
        per_round: list[RoundObservation] = []
        by_agent: dict[str, list[int]] = {}
        for round_resolved in resolved:
            round_number = round_resolved.round_number
            excess = excess_moves_by_agent(started=started[round_number], resolved=round_resolved)
            for agent_id, count in excess.items():
                by_agent.setdefault(agent_id, []).append(count)
            note = "; ".join(
                f"{agent_id}: {count} excess "
                f"[{' '.join(traces.get((round_number, agent_id), [])) or 'no moves'}]"
                for agent_id, count in excess.items()
            )
            per_round.append(
                RoundObservation(
                    round_number=round_number,
                    value=fmean(excess.values()),
                    note=note,
                )
            )
        all_counts = [count for counts in by_agent.values() for count in counts]
        score = fmean(all_counts)
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit="mean excess moves per player per round",
                summary=(
                    f"{score:.2f} excess moves per player-round over {len(resolved)} rounds; "
                    f"{sum(1 for count in all_counts if count > 0)}/{len(all_counts)} "
                    "player-rounds had any"
                ),
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=fmean(counts),
                        note=f"mean excess moves over {len(counts)} rounds",
                    )
                    for agent_id, counts in sorted(by_agent.items())
                ],
            )
        ]
