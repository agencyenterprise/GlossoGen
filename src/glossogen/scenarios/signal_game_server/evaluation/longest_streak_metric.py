"""``longest_streak``: the most rounds a pair won in a row, the score the paper reports.

Scott-Phillips, Kirby & Ritchie (2009) scored each pair by "their highest number
of points scored in succession", so that a pair could not do well through the
number of rounds played. ``round_success`` counts every win; this counts the
longest unbroken run of them. A round missing from the log breaks a run.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase
from glossogen.scenarios.signal_game_server.events import SignalGameServerRoundResolved

logger = logging.getLogger(__name__)


class LongestStreakMetric(Metric):
    """The longest run of consecutive winning rounds, with the running streak per round."""

    name = "longest_streak"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over every resolved round, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        resolved = {
            event.round_number: event
            for event in events
            if isinstance(event, SignalGameServerRoundResolved)
        }
        if not resolved:
            logger.info("longest_streak: no resolved rounds in this run; skipping")
            return []
        per_round: list[RoundObservation] = []
        streak = 0
        longest = 0
        previous_round: int | None = None
        for round_number, outcome in sorted(resolved.items()):
            if previous_round is not None and round_number != previous_round + 1:
                streak = 0
            if outcome.success:
                streak += 1
            else:
                streak = 0
            longest = max(longest, streak)
            previous_round = round_number
            per_round.append(
                RoundObservation(
                    round_number=round_number,
                    value=float(streak),
                    note=f"won: {outcome.success}",
                )
            )
        return [
            Measurement(
                metric_name=self.name,
                score=float(longest),
                score_unit="most consecutive rounds won",
                summary=(
                    f"longest streak {longest} over {len(resolved)} rounds; "
                    f"{sum(1 for outcome in resolved.values() if outcome.success)} won in all"
                ),
                per_round=per_round,
                per_agent=[],
            )
        ]
