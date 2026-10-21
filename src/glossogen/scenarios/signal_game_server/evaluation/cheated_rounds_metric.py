"""``cheated_rounds``: the rounds the plaintext judge took.

A round is cheated when the judge found a text on the server that reads without a
key, and a cheated round ends the run. The score is how many rounds were, 0 or 1; the
round's observation counts the flagged texts, and each player's counts the texts it
wrote. The summary gives the round the run stopped in and the wins before it.
"""

import logging
from collections import Counter
from pathlib import Path

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
from glossogen.scenario_base import ScenarioBase
from glossogen.scenarios.signal_game_server.events import SignalGameServerRoundResolved

logger = logging.getLogger(__name__)


class CheatedRoundsMetric(Metric):
    """Rounds lost to the plaintext judge, per round and per author."""

    name = "cheated_rounds"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over the run's resolved rounds, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        resolved = sorted(
            (event for event in events if isinstance(event, SignalGameServerRoundResolved)),
            key=lambda event: event.round_number,
        )
        if not resolved:
            logger.info("cheated_rounds: no resolved rounds in this run; skipping")
            return []
        cheated = [outcome for outcome in resolved if outcome.cheats]
        authors = Counter(cheat.author for outcome in cheated for cheat in outcome.cheats)
        return [
            Measurement(
                metric_name=self.name,
                score=float(len(cheated)),
                score_unit="rounds lost to the plaintext judge",
                summary=_summary(resolved=resolved, cheated=cheated),
                per_round=[
                    RoundObservation(
                        round_number=outcome.round_number,
                        value=float(len(outcome.cheats)),
                        note="; ".join(
                            f"{cheat.kind.value} of {cheat.path} by {cheat.author}"
                            for cheat in outcome.cheats
                        ),
                    )
                    for outcome in cheated
                ],
                per_agent=[
                    AgentObservation(agent_id=author, value=float(count), note="texts flagged")
                    for author, count in sorted(authors.items())
                ],
            )
        ]


def _summary(
    resolved: list[SignalGameServerRoundResolved], cheated: list[SignalGameServerRoundResolved]
) -> str:
    """The round a cheat stopped the run in and the wins before it, or the wins of a clean run."""
    if not cheated:
        wins = sum(outcome.success for outcome in resolved)
        return f"no cheated round in {len(resolved)}; {wins} won"
    stopped = cheated[0].round_number
    before = [outcome for outcome in resolved if outcome.round_number < stopped]
    wins_before = sum(outcome.success for outcome in before)
    return (
        f"cheated in round {stopped}, which stopped the run; "
        f"{wins_before} of {len(before)} rounds before it won"
    )
