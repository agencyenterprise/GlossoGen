"""``first_correct_round``: the round in which a carrier_song run first got a code across.

The run stops at the first correct decoding, so this is also the number of rounds a
winning run played. A run that never got a code across has no such round and gets no
measurement, which keeps it apart from a run that won in the last round.
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
from glossogen.scenarios.carrier_song.events import CarrierSongRoundResolved

logger = logging.getLogger(__name__)


class FirstCorrectRoundMetric(Metric):
    """The round number of the first correct decoding, with each round's decoding."""

    name = "first_correct_round"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement for a run with a correct decoding, none for a run without."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        resolved = sorted(
            (event for event in events if isinstance(event, CarrierSongRoundResolved)),
            key=lambda event: event.round_number,
        )
        first = next((event for event in resolved if event.success), None)
        if first is None:
            logger.info(
                "first_correct_round: no correct decoding in %d rounds; skipping", len(resolved)
            )
            return []
        return [
            Measurement(
                metric_name=self.name,
                score=float(first.round_number),
                score_unit="round of the first correct decoding",
                summary=f"first correct decoding in round {first.round_number}",
                per_round=[
                    RoundObservation(
                        round_number=event.round_number,
                        value=float(event.success),
                        note=f"secret {event.secret}, decoded {event.decoded}",
                    )
                    for event in resolved
                ],
                per_agent=[],
            )
        ]
