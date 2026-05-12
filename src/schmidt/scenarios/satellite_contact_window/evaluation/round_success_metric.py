"""Metric that counts how many satellite contact-window rounds were recovered.

A round succeeds when the telemetry operator's ``send_command_sequence``
call earns a positive ``SatelliteCommandSequenceJudged`` event (all six
judge criteria true) before the contact window closes.
"""

import logging
from pathlib import Path

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import RoundAdvanced, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.satellite_contact_window.events import SatelliteCommandSequenceJudged

logger = logging.getLogger(__name__)


class RoundSuccessMetric(Metric):
    """Counts rounds where the satellite was successfully recovered.

    Emits one Measurement (``metric_name="round_success"``) whose ``score``
    is the fraction of rounds with a successful recovery. ``per_round``
    carries one observation per round with the recovery outcome.
    """

    name = "round_success"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score rounds using ``SatelliteCommandSequenceJudged`` events."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        total_rounds = _count_total_rounds(events=events)
        if total_rounds == 0:
            return []

        latest_judged: dict[int, SatelliteCommandSequenceJudged] = {}
        for event in events:
            if isinstance(event, SatelliteCommandSequenceJudged):
                latest_judged[event.round_number] = event

        won = 0
        per_round: list[RoundObservation] = []
        for round_number in range(1, total_rounds + 1):
            judged = latest_judged.get(round_number)
            if judged is None:
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=0.0,
                        note="no send_command_sequence call",
                    )
                )
                continue
            if judged.overall_success:
                won += 1
                per_round.append(
                    RoundObservation(
                        round_number=round_number,
                        value=1.0,
                        note="recovered",
                    )
                )
                continue
            if judged.budget_exceeded:
                note = "contact window closed; judge approved but too late"
            else:
                if len(judged.violations) > 0:
                    violation_summary = "; ".join(judged.violations)
                    note = f"judge rejected: {violation_summary}"
                else:
                    note = f"judge rejected: {judged.judge_explanation}"
            per_round.append(
                RoundObservation(
                    round_number=round_number,
                    value=0.0,
                    note=note,
                )
            )

        score = won / total_rounds
        return [
            Measurement(
                metric_name=self.name,
                score=score,
                score_unit=f"fraction of rounds recovered ({won}/{total_rounds})",
                summary=f"recovered in {won}/{total_rounds} rounds",
                per_round=per_round,
                per_agent=[],
            )
        ]


def _count_total_rounds(events: list[SimulationEvent]) -> int:
    """Return the highest round number observed in ``RoundAdvanced`` events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    return max_round
