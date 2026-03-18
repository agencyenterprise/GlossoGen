"""Incident response simulation scenario.

Defines a three-agent scenario (Engineer, Support Lead, PM) that
simulates an incident war room. Agents communicate through a shared
war-room channel and pairwise private sidebar channels. The simulation
runs for a fixed number of rounds, each consisting of war-room turns
followed by scheduled private sidebar turns.
"""

import argparse
import logging
from pathlib import Path
from typing import Self

from jinja2 import Environment, FileSystemLoader

from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult, write_report
from schmidt.evaluation.evaluator_registry import GENERIC_EVALUATOR_REGISTRY
from schmidt.evaluation.log_reader import extract_agent_configs, extract_simulation_id, load_events
from schmidt.llm.claude_provider import ClaudeProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.models.tool_definition import ToolParameter, ToolSpec
from schmidt.scenario_protocol import SimulationScenario
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

ENGINEER_ID = "engineer"
SUPPORT_LEAD_ID = "support_lead"
PM_ID = "pm"

WAR_ROOM_ID = "war-room"
ENG_SUPPORT_ID = "eng-support"
ENG_PM_ID = "eng-pm"
SUPPORT_PM_ID = "support-pm"

MAX_ROUNDS = 6

PROPOSE_RESOLUTION_SPEC = ToolSpec(
    name="propose_resolution",
    description="Propose a resolution for the incident with a diagnosis and fix plan.",
    parameters=[
        ToolParameter(
            name="diagnosis",
            param_type="string",
            description="The root cause diagnosis.",
            required=True,
        ),
        ToolParameter(
            name="fix_plan",
            param_type="string",
            description="The proposed fix plan.",
            required=True,
        ),
        ToolParameter(
            name="estimated_hours",
            param_type="integer",
            description="Estimated hours to implement the fix.",
            required=True,
        ),
    ],
)

CHANNEL_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    WAR_ROOM_ID: {
        ENGINEER_ID: "incident war room",
        SUPPORT_LEAD_ID: "incident war room",
        PM_ID: "incident war room",
    },
    ENG_SUPPORT_ID: {
        ENGINEER_ID: "private conversation with the support lead",
        SUPPORT_LEAD_ID: "private conversation with the engineer",
    },
    ENG_PM_ID: {
        ENGINEER_ID: "private conversation with the PM",
        PM_ID: "private conversation with the engineer",
    },
    SUPPORT_PM_ID: {
        SUPPORT_LEAD_ID: "private conversation with the PM",
        PM_ID: "private conversation with the support lead",
    },
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    ENGINEER_ID: "Engineer",
    SUPPORT_LEAD_ID: "Support Lead",
    PM_ID: "PM",
}

WAR_ROOM_ORDER = [PM_ID, ENGINEER_ID, SUPPORT_LEAD_ID]

PRIVATE_SIDEBARS: dict[int, list[tuple[str, str]]] = {
    1: [],
    2: [(ENG_PM_ID, ENGINEER_ID)],
    3: [(SUPPORT_PM_ID, SUPPORT_LEAD_ID)],
    4: [(ENG_PM_ID, PM_ID), (ENG_SUPPORT_ID, SUPPORT_LEAD_ID)],
    5: [(ENG_PM_ID, ENGINEER_ID)],
    6: [(ENG_PM_ID, PM_ID)],
}

AGENT_SYSTEM_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_system.jinja",
    SUPPORT_LEAD_ID: "support_lead_system.jinja",
    PM_ID: "pm_system.jinja",
}


AGENT_INJECTION_TEMPLATES: dict[str, str] = {
    ENGINEER_ID: "engineer_injection.jinja",
    SUPPORT_LEAD_ID: "support_lead_injection.jinja",
    PM_ID: "pm_injection.jinja",
}


class IncidentResponseScenario(SimulationScenario):
    """Simulation scenario for a three-agent incident response war room.

    Manages agent configuration, channel layout, turn ordering, prompt
    rendering, and tool registration for the incident response simulation.
    Turn scheduling follows a fixed round structure: each round has all
    agents speak in the war room, then selected agents participate in
    private sidebar channels according to a per-round schedule.
    """

    @classmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:  # noqa: ARG003
        """No scenario-specific CLI arguments needed."""

    @classmethod
    def create(cls, args: argparse.Namespace) -> Self:  # noqa: ARG003
        """Construct the scenario. No CLI arguments are used."""
        return cls()

    def __init__(self) -> None:
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
        return "incident_response"

    def scenario_description(self) -> str:
        """Return a markdown description of the incident response scenario."""
        return self._render_template(template_name="description.jinja")

    def _channel_template_data(
        self, agent_id: str, channel_ids: list[str]
    ) -> list[ChannelTemplateEntry]:
        """Build a list of channel entries with display_name and
        channel_id for use in Jinja2 system prompt templates.
        """
        return [
            ChannelTemplateEntry(
                display_name=self.get_channel_display_name(channel_id=cid, agent_id=agent_id),
                channel_id=cid,
            )
            for cid in channel_ids
        ]

    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return agent configurations for the Engineer, Support
        Lead, and PM.

        Each agent is configured with a system prompt rendered from
        its Jinja2 template, the channels it can participate in,
        and its available tools.
        """
        agent_defs: list[tuple[str, str, list[str]]] = [
            (ENGINEER_ID, "Engineer", [WAR_ROOM_ID, ENG_SUPPORT_ID, ENG_PM_ID]),
            (SUPPORT_LEAD_ID, "Support Lead", [WAR_ROOM_ID, ENG_SUPPORT_ID, SUPPORT_PM_ID]),
            (PM_ID, "PM", [WAR_ROOM_ID, ENG_PM_ID, SUPPORT_PM_ID]),
        ]
        agents: list[AgentConfig] = []
        for agent_id, role_name, channel_ids in agent_defs:
            agents.append(
                AgentConfig(
                    agent_id=agent_id,
                    role_name=role_name,
                    system_prompt=self._render_template(
                        template_name=AGENT_SYSTEM_TEMPLATES[agent_id],
                        channels=self._channel_template_data(
                            agent_id=agent_id, channel_ids=channel_ids
                        ),
                    ),
                    channel_ids=channel_ids,
                    tool_names=["send_message", "propose_resolution"],
                    model=default_model,
                )
            )
        return agents

    def get_channels(self) -> list[Channel]:
        """Return the four communication channels: one shared war
        room and three pairwise private channels.
        """
        return [
            Channel(
                channel_id=WAR_ROOM_ID,
                name="war-room",
                member_agent_ids=[ENGINEER_ID, SUPPORT_LEAD_ID, PM_ID],
            ),
            Channel(
                channel_id=ENG_SUPPORT_ID,
                name="eng-support",
                member_agent_ids=[ENGINEER_ID, SUPPORT_LEAD_ID],
            ),
            Channel(
                channel_id=ENG_PM_ID,
                name="eng-pm",
                member_agent_ids=[ENGINEER_ID, PM_ID],
            ),
            Channel(
                channel_id=SUPPORT_PM_ID,
                name="support-pm",
                member_agent_ids=[SUPPORT_LEAD_ID, PM_ID],
            ),
        ]

    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name for a channel as seen by a specific agent.

        Private channels are described from the agent's perspective
        (e.g. "private conversation with the PM"). Falls back to the
        raw channel_id if no mapping exists.
        """
        return CHANNEL_DISPLAY_NAMES.get(channel_id, {}).get(agent_id, channel_id)

    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent. Falls back to the raw agent_id."""
        return AGENT_DISPLAY_NAMES.get(agent_id, agent_id)

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:  # noqa: ARG002
        """Return the next turn decision, or None to end the simulation.

        Iterates through pre-built turns for the current round. When all
        turns in a round are exhausted, advances to the next round and
        builds its turn list. Returns None when all rounds have been completed.

        ``state`` is accepted to satisfy the SimulationScenario protocol but
        is unused here because this scenario uses a fixed round schedule
        rather than adaptive turn logic.
        """
        if self._turn_index < len(self._current_round_turns):
            decision = self._current_round_turns[self._turn_index]
            self._turn_index += 1
            return decision

        self._current_round += 1
        if self._current_round > MAX_ROUNDS:
            logger.info("All %d rounds completed", MAX_ROUNDS)
            return None

        self._current_round_turns = self._build_round_turns(round_number=self._current_round)
        self._turn_index = 0
        logger.info(
            "Starting round %d/%d with %d turns",
            self._current_round,
            MAX_ROUNDS,
            len(self._current_round_turns),
        )

        decision = self._current_round_turns[self._turn_index]
        self._turn_index += 1
        return decision

    def _build_round_turns(self, round_number: int) -> list[TurnDecision]:
        """Build the ordered list of turns for a given round.

        Each round starts with all agents speaking in the war room (in
        WAR_ROOM_ORDER), followed by any private sidebar turns scheduled
        for that round in PRIVATE_SIDEBARS.
        """
        turns: list[TurnDecision] = []

        for agent_id in WAR_ROOM_ORDER:
            turns.append(
                TurnDecision(
                    agent_id=agent_id,
                    channel_id=WAR_ROOM_ID,
                    round_number=round_number,
                )
            )

        sidebars = PRIVATE_SIDEBARS.get(round_number, [])
        for channel_id, agent_id in sidebars:
            turns.append(
                TurnDecision(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    round_number=round_number,
                )
            )

        return turns

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return the injection message for an agent at a given round, or None if empty.

        Renders the agent's injection Jinja2 template with the current
        round number. Returns None if the agent has no injection template
        or if the rendered result is empty.
        """
        template_name = AGENT_INJECTION_TEMPLATES.get(agent_id)
        if template_name is None:
            return None

        rendered = self._render_template(template_name=template_name, round_number=round_number)
        if not rendered:
            return None
        logger.debug(
            "Injection for agent %s at round %d: %d chars", agent_id, round_number, len(rendered)
        )
        return rendered

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register scenario-specific tools with the tool registry.

        Registers the ``propose_resolution`` tool, which allows agents
        to submit a diagnosis, fix plan, and time estimate for the incident.
        """

        async def propose_resolution(
            agent_id: str, diagnosis: str, fix_plan: str, estimated_hours: int
        ) -> str:
            return (
                f"Resolution proposed by {agent_id}: "
                f"Diagnosis: {diagnosis}. "
                f"Fix: {fix_plan}. "
                f"ETA: {estimated_hours}h"
            )

        registry.register(spec=PROPOSE_RESOLUTION_SPEC, executor=propose_resolution)
        logger.debug("Registered scenario tool: propose_resolution")

    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
    ) -> EvaluationReport:
        """Run evaluators and write a JSON report."""
        events = await load_events(log_path=log_path)
        agent_configs = extract_agent_configs(events=events)
        simulation_id = extract_simulation_id(events=events)
        provider = ClaudeProvider(model=model)

        metrics: list[MetricResult] = []
        for name in evaluator_names:
            if name not in GENERIC_EVALUATOR_REGISTRY:
                available = ", ".join(sorted(GENERIC_EVALUATOR_REGISTRY.keys()))
                raise ValueError(f"Unknown evaluator: '{name}'. Available: {available}")
            evaluator = GENERIC_EVALUATOR_REGISTRY[name]()
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
