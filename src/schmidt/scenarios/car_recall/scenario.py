"""Car recall simulation scenario.

Defines a multi-agent scenario (3 or 5 agents) that simulates a corporate
recall decision. Internal agents deliberate through a shared internal channel
while (in 5-agent mode) the PR agent writes summary reports to the Regulator
on a separate channel. The Regulator has no access to the internal discussion
and can only respond to PR's reports.

Each round starts an internal discussion where agents rotate until all pass
or the max_turns_per_round knob is reached. Agent order is shuffled between
rotations. On scheduled rounds, a regulator report discussion follows with
the same rotation-until-all-pass model. The simulation runs for 3 or 5
rounds depending on the time_pressure knob.
"""

import argparse
import logging
import random
from pathlib import Path
from typing import Any, Self

from jinja2 import Environment, FileSystemLoader

from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.provider_factory import create_provider
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
        self._discussion_agents: list[str] = []
        self._discussion_channel: str = ""
        self._rotation_index: int = -1
        self._anyone_spoke_this_rotation: bool = False
        self._regulator_queue: list[tuple[str, list[str]]] = []
        self._discussion_started: bool = False
        self._first_rotation: bool = True
        self._turns_this_round: int = 0
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
            (ENGINEER_ID, "Engineer", [INTERNAL_ID], ["send_message", "pass_turn", "think"]),
            (LEGAL_ID, "Legal", [INTERNAL_ID], ["send_message", "pass_turn", "think"]),
        ]

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append((CFO_ID, "CFO", [INTERNAL_ID], ["send_message", "pass_turn", "think"]))

        pr_channels = [INTERNAL_ID]
        if self._knobs.agent_count == AgentCount.FIVE:
            pr_channels.append(REGULATOR_REPORT_ID)
        defs.append((PR_ID, "PR", pr_channels, ["send_message", "pass_turn", "think"]))

        if self._knobs.agent_count == AgentCount.FIVE:
            defs.append(
                (
                    REGULATOR_ID,
                    "Regulator",
                    [REGULATOR_REPORT_ID],
                    ["send_message", "pass_turn", "think"],
                )
            )

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

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Return the next turn decision, or None to end the simulation.

        Rotates agents in the current discussion (internal or regulator report)
        until all agents pass in a full rotation or the turn cap is reached.
        Then advances to the next discussion phase or next round.
        """
        if self._discussion_started:
            self._turns_this_round += 1
            self._record_turn_outcome(passed=state.last_turn_passed)
            result = self._advance_rotation()
            if result is not None:
                return result

        return self._start_next_discussion()

    def _record_turn_outcome(self, passed: bool) -> None:
        """Record whether the last agent spoke or passed."""
        last_agent = self._discussion_agents[self._rotation_index]
        if passed:
            logger.info("Agent %s passed on %s", last_agent, self._discussion_channel)
        else:
            self._anyone_spoke_this_rotation = True
            logger.info("Agent %s spoke on %s", last_agent, self._discussion_channel)

    def _advance_rotation(self) -> TurnDecision | None:
        """Move to the next agent in the current rotation.

        Returns the next TurnDecision, or None if the discussion
        ended (all agents passed in a full rotation or the turn cap is reached).
        """
        # Check turn cap before continuing
        if self._turns_this_round >= self._knobs.max_turns_per_round:
            logger.info(
                "Round %d reached max turns (%d), ending discussion on %s",
                self._current_round,
                self._knobs.max_turns_per_round,
                self._discussion_channel,
            )
            self._discussion_started = False
            return None

        self._rotation_index += 1
        if self._rotation_index < len(self._discussion_agents):
            return self._current_turn_decision()

        # Full rotation completed
        if not self._anyone_spoke_this_rotation:
            logger.info(
                "All agents passed on %s, ending discussion",
                self._discussion_channel,
            )
            self._discussion_started = False
            return None

        # Start a new rotation with shuffled order
        self._shuffle_agents()
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = False
        logger.info("New rotation on %s: %s", self._discussion_channel, self._discussion_agents)
        return self._current_turn_decision()

    def _shuffle_agents(self) -> None:
        """Shuffle the discussion agent order for the next rotation.

        The last agent in the previous rotation is excluded from the
        first position to avoid back-to-back turns.
        """
        last_agent = self._discussion_agents[-1]
        others = [a for a in self._discussion_agents if a != last_agent]
        random.shuffle(others)
        insert_index = random.randint(1, len(others))
        others.insert(insert_index, last_agent)
        self._discussion_agents = others

    def _current_turn_decision(self) -> TurnDecision:
        """Build a TurnDecision for the current rotation position."""
        return TurnDecision(
            agent_id=self._discussion_agents[self._rotation_index],
            round_number=self._current_round,
            allow_pass=not self._first_rotation,
        )

    def _start_next_discussion(self) -> TurnDecision | None:
        """Start the next discussion phase: a regulator report from the queue, or
        the internal discussion of the next round. Returns None when all rounds are done.
        """
        if self._regulator_queue:
            channel_id, agents = self._regulator_queue.pop(0)
            return self._begin_discussion(channel_id=channel_id, agents=agents)

        self._current_round += 1
        if self._current_round > self._max_rounds:
            logger.info("All %d rounds completed", self._max_rounds)
            return None

        self._turns_this_round = 0

        # Build regulator discussion queue for this round
        self._regulator_queue = self._build_regulator_queue(round_number=self._current_round)

        logger.info(
            "Starting round %d/%d (day %d) — internal + %d regulator discussions",
            self._current_round,
            self._max_rounds,
            self._day_map[self._current_round],
            len(self._regulator_queue),
        )

        return self._begin_discussion(
            channel_id=INTERNAL_ID,
            agents=self._internal_turn_order(),
        )

    def _begin_discussion(self, channel_id: str, agents: list[str]) -> TurnDecision:
        """Initialize a new rotation discussion on a channel."""
        self._discussion_channel = channel_id
        self._discussion_agents = agents
        self._rotation_index = 0
        self._anyone_spoke_this_rotation = False
        self._first_rotation = True
        self._discussion_started = True
        logger.info("Starting discussion on %s with agents: %s", channel_id, agents)
        return self._current_turn_decision()

    def _build_regulator_queue(self, round_number: int) -> list[tuple[str, list[str]]]:
        """Build the regulator report discussion queue for a round.

        Returns a list of (channel_id, [agent_ids]) pairs for regulator
        discussions scheduled this round.
        """
        raw_turns = self._regulator_turns_for_round(round_number=round_number)
        if not raw_turns:
            return []
        queue = [(REGULATOR_REPORT_ID, [PR_ID, REGULATOR_ID])]
        logger.info("Queued %d regulator discussion(s) for round %d", len(queue), round_number)
        return queue

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

    def get_checkpoint(self) -> dict[str, Any]:
        """Serialize the scenario's turn-scheduling state for resume."""
        return {
            "current_round": self._current_round,
            "discussion_agents": list(self._discussion_agents),
            "discussion_channel": self._discussion_channel,
            "rotation_index": self._rotation_index,
            "anyone_spoke_this_rotation": self._anyone_spoke_this_rotation,
            "regulator_queue": [
                {"channel_id": ch, "agents": agents} for ch, agents in self._regulator_queue
            ],
            "discussion_started": self._discussion_started,
            "first_rotation": self._first_rotation,
            "turns_this_round": self._turns_this_round,
        }

    def restore_from_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore the scenario's turn-scheduling state from a checkpoint."""
        self._current_round = checkpoint["current_round"]
        self._discussion_agents = checkpoint["discussion_agents"]
        self._discussion_channel = checkpoint["discussion_channel"]
        self._rotation_index = checkpoint["rotation_index"]
        self._anyone_spoke_this_rotation = checkpoint["anyone_spoke_this_rotation"]
        self._regulator_queue = [
            (item["channel_id"], item["agents"]) for item in checkpoint["regulator_queue"]
        ]
        self._discussion_started = checkpoint["discussion_started"]
        self._first_rotation = checkpoint["first_rotation"]
        self._turns_this_round = checkpoint["turns_this_round"]
        logger.info(
            "Restored scenario state: round=%d, discussion_started=%s",
            self._current_round,
            self._discussion_started,
        )

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
        reasoning_effort: str | None,
    ) -> EvaluationReport:
        """Run evaluators, compute derived flags, and write a JSON report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = create_provider(model=model, reasoning_effort=reasoning_effort)

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
