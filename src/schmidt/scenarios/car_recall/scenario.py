"""Car recall simulation scenario.

Defines a multi-agent scenario (3 or 5 agents) that simulates a corporate
recall decision. Internal agents deliberate through a shared internal channel
while (in 5-agent mode) the PR agent writes summary reports to the Regulator
on a separate channel. The Regulator has no access to the internal discussion
and can only respond to PR's reports.

The simulation runs for 3 or 5 fixed rounds (days) depending on the time
pressure knob. The correct decision — full recall — requires all three
private facts to surface and be integrated.
"""

import argparse
import logging
from pathlib import Path
from typing import Self

from jinja2 import Environment, FileSystemLoader

from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.car_recall.channel_ids import INTERNAL_ID, REGULATOR_REPORT_ID
from schmidt.scenarios.car_recall.evaluation import (
    DecisionCorrectnessEvaluator,
    FactSurfacingEvaluator,
    ReportDivergenceEvaluator,
)
from schmidt.scenarios.car_recall.knobs import AgentCount, CarRecallKnobs, TimePressure
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

ENGINEER_ID = "engineer"
LEGAL_ID = "legal"
CFO_ID = "cfo"
PR_ID = "pr"
REGULATOR_ID = "regulator"

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    INTERNAL_ID: {
        ENGINEER_ID: "internal group discussion",
        LEGAL_ID: "internal group discussion",
        CFO_ID: "internal group discussion",
        PR_ID: "internal group discussion",
    },
    REGULATOR_REPORT_ID: {
        PR_ID: "regulator report channel",
        REGULATOR_ID: "regulator report channel",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    ENGINEER_ID: "Engineer",
    LEGAL_ID: "Legal",
    CFO_ID: "CFO",
    PR_ID: "PR",
    REGULATOR_ID: "Regulator",
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_system.jinja",
    LEGAL_ID: "legal_system.jinja",
    CFO_ID: "cfo_system.jinja",
    PR_ID: "pr_system.jinja",
    REGULATOR_ID: "regulator_system.jinja",
}

AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_injection.jinja",
    LEGAL_ID: "legal_injection.jinja",
    CFO_ID: "cfo_injection.jinja",
    PR_ID: "pr_injection.jinja",
    REGULATOR_ID: "regulator_injection.jinja",
}

# Maps round number -> simulated day number. High pressure skips days 2
# and 4, compressing the 5-day timeline into 3 rounds.
LOW_PRESSURE_DAY_MAP: dict[int, int] = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
HIGH_PRESSURE_DAY_MAP: dict[int, int] = {1: 1, 2: 3, 3: 5}


class CarRecallScenario(SimulationScenario):
    """Simulation scenario for a car recall decision.

    Supports 3-agent mode (Engineer, Legal, PR) or 5-agent mode
    (adding CFO and Regulator). Behavior is controlled by the
    ``CarRecallKnobs`` configuration object passed at construction.
    """

    @classmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Register the ``--knobs`` argument required by this scenario."""
        parser.add_argument(
            "--knobs",
            type=str,
            required=True,
            help="Path to a JSON file with car recall scenario knobs",
        )

    @classmethod
    def create(cls, args: argparse.Namespace) -> Self:
        """Read the knobs JSON file and construct the scenario."""
        knobs_json = Path(args.knobs).read_text()
        knobs = CarRecallKnobs.model_validate_json(knobs_json)
        return cls(knobs=knobs)

    def __init__(self, knobs: CarRecallKnobs) -> None:
        self._knobs = knobs
        if knobs.time_pressure == TimePressure.HIGH:
            self._max_rounds = 3
            self._day_map = HIGH_PRESSURE_DAY_MAP
        else:
            self._max_rounds = 5
            self._day_map = LOW_PRESSURE_DAY_MAP
        self._current_round = 0
        self._turn_index = 0
        self._current_round_turns: list[TurnDecision] = []
        self._jinja = Environment(
            loader=FileSystemLoader(PROMPTS_DIR),
            autoescape=False,
            keep_trailing_newline=False,
        )

    def _render_template(self, template_name: str, **kwargs: object) -> str:
        """Render a Jinja2 template from the scenario prompts directory."""
        template = self._jinja.get_template(name=template_name)
        return template.render(**kwargs).strip()

    def name(self) -> str:
        """Return the scenario identifier."""
        return "car_recall"

    def scenario_description(self) -> str:
        """Return a markdown description reflecting the active knobs."""
        return self._render_template(
            template_name="description.jinja",
            knobs=self._knobs,
            max_rounds=self._max_rounds,
            five=self._knobs.agent_count == AgentCount.FIVE,
        )

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build a list of channel entries for Jinja2 system prompt templates."""
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def _internal_turn_order(self) -> list[str]:
        """Return the ordered list of agent IDs for internal channel turns."""
        if self._knobs.agent_count == AgentCount.THREE:
            return [ENGINEER_ID, LEGAL_ID, PR_ID]
        return [ENGINEER_ID, LEGAL_ID, CFO_ID, PR_ID]

    def _regulator_turns_for_round(self, round_number: int) -> list[tuple[str, str]]:
        """Return the (channel_id, agent_id) pairs for regulator-report turns in a round."""
        if self._knobs.agent_count == AgentCount.THREE:
            return []

        day = self._day_map[round_number]

        if self._knobs.time_pressure == TimePressure.HIGH:
            if day == 3:
                return [(REGULATOR_REPORT_ID, PR_ID), (REGULATOR_REPORT_ID, REGULATOR_ID)]
        else:
            if day in (3, 4):
                return [(REGULATOR_REPORT_ID, PR_ID), (REGULATOR_REPORT_ID, REGULATOR_ID)]
        return []

    def _agent_defs(self) -> list[tuple[str, str, list[str], list[str]]]:
        """Build agent definition tuples based on knobs."""
        defs: list[tuple[str, str, list[str], list[str]]] = [
            (ENGINEER_ID, "Engineer", [INTERNAL_ID], ["send_message"]),
            (LEGAL_ID, "Legal", [INTERNAL_ID], ["send_message"]),
        ]

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append((CFO_ID, "CFO", [INTERNAL_ID], ["send_message"]))

        pr_channels = [INTERNAL_ID]
        if self._knobs.agent_count == AgentCount.FIVE:
            pr_channels.append(REGULATOR_REPORT_ID)
        defs.append((PR_ID, "PR", pr_channels, ["send_message"]))

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append((REGULATOR_ID, "Regulator", [REGULATOR_REPORT_ID], ["send_message"]))

        return defs

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations based on the knobs."""
        agents: list[AgentConfig] = []
        for agent_id, role_name, channel_ids, tool_names in self._agent_defs():
            model = self._knobs.model_overrides.get(agent_id, default_model)
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=role_name,
                    system_prompt=self._render_template(
                        template_name=AGENT_SYSTEM_TEMPLATES[agent_id],
                        channels=self._channel_template_data(
                            agent_id=agent_id, channel_ids=channel_ids
                        ),
                        knobs=self._knobs,
                    ),
                    channel_ids=channel_ids,
                    tool_names=tool_names,
                    model=model,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the communication channels based on agent count."""
        channels = [
            Channel(
                channel_id=INTERNAL_ID,
                name="internal",
                member_agent_ids=self._internal_turn_order(),
            ),
        ]
        if self._knobs.agent_count == AgentCount.FIVE:
            channels.append(
                Channel(
                    channel_id=REGULATOR_REPORT_ID,
                    name="regulator-report",
                    member_agent_ids=[PR_ID, REGULATOR_ID],
                ),
            )
        return channels

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent."""
        return CHANNEL_DISPLAY_NAMES.get(channel_id, {}).get(agent_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        return AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:  # noqa: ARG002
        """Return the next turn decision, or None to end the simulation.

        Each round starts with all internal agents speaking on the internal
        channel, then any scheduled regulator-report turns. Returns None
        when all rounds are completed.
        """
        if self._turn_index < len(self._current_round_turns):
            decision = self._current_round_turns[self._turn_index]
            self._turn_index += 1
            return decision

        while self._current_round < self._max_rounds:
            self._current_round += 1
            self._current_round_turns = self._build_round_turns(round_number=self._current_round)
            self._turn_index = 0

            if not self._current_round_turns:
                logger.info(
                    "Round %d/%d has no turns, skipping",
                    self._current_round,
                    self._max_rounds,
                )
                continue

            logger.info(
                "Starting round %d/%d (day %d) with %d turns",
                self._current_round,
                self._max_rounds,
                self._day_map[self._current_round],
                len(self._current_round_turns),
            )
            decision = self._current_round_turns[self._turn_index]
            self._turn_index += 1
            return decision

        logger.info("All %d rounds completed", self._max_rounds)
        return None

    def _build_round_turns(self, round_number: int) -> list[TurnDecision]:
        """Build the ordered list of turns for a given round.

        Each round starts with all internal agents speaking in turn order,
        followed by any regulator-report turns scheduled for that round's day.
        """
        turns: list[TurnDecision] = []

        for agent_id in self._internal_turn_order():
            turns.append(
                TurnDecision(
                    agent_id=agent_id,
                    channel_id=INTERNAL_ID,
                    round_number=round_number,
                )
            )

        for channel_id, agent_id in self._regulator_turns_for_round(round_number=round_number):
            turns.append(
                TurnDecision(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    round_number=round_number,
                )
            )

        return turns

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection message for an agent at a given round, or None if empty."""
        template_name = AGENT_INJECTION_TEMPLATES.get(agent_id)
        if template_name is None:
            return None

        day_number = self._day_map[round_number]
        rendered = self._render_template(
            template_name=template_name,
            day_number=day_number,
            knobs=self._knobs,
        )
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d (day %d): %d chars",
            agent_id,
            round_number,
            day_number,
            len(rendered),
        )
        return rendered

    def register_tools(self, registry: ToolRegistry) -> None:  # noqa: ARG002
        """No scenario-specific tools are registered for the car recall scenario."""

    def _get_evaluators(self) -> dict[str, type[Evaluator]]:
        """Return car recall-specific evaluators."""
        return {
            "fact_surfacing": FactSurfacingEvaluator,
            "report_divergence": ReportDivergenceEvaluator,
            "decision_correctness": DecisionCorrectnessEvaluator,
        }

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
    ) -> EvaluationReport:
        """Run evaluators, compute derived flags, and write a JSON report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = ClaudeProvider(model=model)

        registry: dict[str, type[Evaluator]] = {}
        registry.update(GENERIC_EVALUATOR_REGISTRY)
        registry.update(self._get_evaluators())

        metrics: list[MetricResult] = []
        for name in evaluator_names:
            if name not in registry:
                available = ", ".join(sorted(registry.keys()))
                raise ValueError(f"Unknown evaluator: '{name}'. Available: {available}")
            evaluator = registry[name]()
            logger.info("Running evaluator: %s", name)
            result = await evaluator.evaluate(
                events=events,
                agent_configs=agent_configs,
                scenario=self,
                llm_provider=provider,
            )
            logger.info(
                "Evaluator %s finished: verdict=%s, score=%.2f",
                name,
                result.verdict,
                result.score,
            )
            metrics.append(result)

        report = EvaluationReport(
            simulation_id=simulation_id,
            scenario_name=self.name(),
            metrics=metrics,
        )
        await write_report(report=report, report_path=report_path)
        return report
