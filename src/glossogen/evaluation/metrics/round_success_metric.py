"""Generic metric counting rounds the scenario judged as successful.

Reads ``RoundResultRecorded`` events written by the game clock from
:meth:`SimulationScenario.judge_round_result`. Scenario-agnostic: any
scenario that overrides ``judge_round_result`` automatically gets a
``round_success`` measurement. Multi-team scenarios emit one event per
team per round (each with a populated ``team_id``); this metric emits
one Measurement per team named ``round_success_{team_id}``.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import RoundResultRecorded, SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundSuccessMetric(Metric):
    """Counts rounds the scenario judged as successful.

    Emits one Measurement (``metric_name="round_success"``) when every
    ``RoundResultRecorded`` event has ``team_id=None``. Multi-team
    scenarios emit one Measurement per distinct ``team_id`` named
    ``round_success_{team_id}``. Returns ``[]`` when the run has no
    ``RoundResultRecorded`` events (scenario didn't opt in).
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
        """Group RoundResultRecorded events by team_id and tally success."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        results_by_team: dict[str | None, list[RoundResultRecorded]] = {}
        for event in events:
            if isinstance(event, RoundResultRecorded):
                results_by_team.setdefault(event.team_id, []).append(event)
        if not results_by_team:
            return []
        measurements: list[Measurement] = []
        for team_id, team_results in sorted(
            results_by_team.items(), key=lambda item: (item[0] is not None, item[0])
        ):
            measurements.append(_build_measurement(team_id=team_id, results=team_results))
        return measurements


def _build_measurement(team_id: str | None, results: list[RoundResultRecorded]) -> Measurement:
    """Build one Measurement from a single team's round result events."""
    total = len(results)
    won = sum(1 for r in results if r.success)
    score = won / total if total > 0 else 0.0
    if team_id is None:
        metric_name = "round_success"
    else:
        metric_name = f"round_success_{team_id}"
    per_round = [
        RoundObservation(
            round_number=result.round_number,
            value=1.0 if result.success else 0.0,
            note=result.reason,
        )
        for result in sorted(results, key=lambda r: r.round_number)
    ]
    return Measurement(
        metric_name=metric_name,
        score=score,
        score_unit=f"fraction of rounds succeeded ({won}/{total})",
        summary=f"succeeded in {won}/{total} rounds",
        per_round=per_round,
        per_agent=[],
    )
