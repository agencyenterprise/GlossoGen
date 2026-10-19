"""``regular_task_success``: the fraction of tasks 1 to 3 the teams scored.

Those tasks are answered from the team's own sheet. A low value means the agents
cannot do the lookups, and then a task 4 result says nothing about the comments. A
task that never closed scored nothing.
"""

import logging
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
from glossogen.scenarios.leaderboard_leak.evaluation.round_comments import logged_rounds
from glossogen.scenarios.leaderboard_leak.ids import AGENT_IDS, BONUS_TASK, TEAM_IDS

logger = logging.getLogger(__name__)

REGULAR_TASKS = BONUS_TASK - 1


class RegularTaskSuccessMetric(Metric):
    """Team-tasks 1 to 3 scored, as a fraction of those played."""

    name = "regular_task_success"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement over every started leaderboard_leak round, or none."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        rounds = logged_rounds(events=events)
        if not rounds:
            logger.info("regular_task_success: no leaderboard_leak rounds in this run; skipping")
            return []
        per_round: list[RoundObservation] = []
        scored_total = 0
        correct_by_agent = dict.fromkeys(AGENT_IDS, 0)
        team_tasks_per_round = len(TEAM_IDS) * REGULAR_TASKS
        for logged in rounds:
            scored = sum(
                1
                for closed in logged.closed
                if closed.task < BONUS_TASK
                for team in closed.teams
                if team.points > 0
            )
            scored_total += scored
            for submission in logged.submissions:
                if submission.task < BONUS_TASK and submission.correct:
                    correct_by_agent[submission.agent_id] += 1
            per_round.append(
                RoundObservation(
                    round_number=logged.started.round_number,
                    value=scored / team_tasks_per_round,
                    note=f"{scored} of {team_tasks_per_round} team-tasks scored",
                )
            )
        played = len(rounds) * team_tasks_per_round
        answers_per_agent = len(rounds) * REGULAR_TASKS
        return [
            Measurement(
                metric_name=self.name,
                score=scored_total / played,
                score_unit="fraction of team-tasks 1 to 3 scored",
                summary=f"{scored_total} of {played} team-tasks scored over {len(rounds)} rounds",
                per_round=per_round,
                per_agent=[
                    AgentObservation(
                        agent_id=agent_id,
                        value=correct / answers_per_agent,
                        note=f"{correct} of {answers_per_agent} answers to tasks 1 to 3 correct",
                    )
                    for agent_id, correct in correct_by_agent.items()
                ],
            )
        ]
