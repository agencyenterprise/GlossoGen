"""A small scenario used only by tests.

Real scenarios carry domain rules that muddy an assertion about the platform. A
failing test should say the platform broke, not that a Veyru was mis-stabilised.
This one has two agents, one channel, and a custom tool that records whatever it
is handed.

It also implements the optional hooks a scenario uses to opt into the
communication and protocol-probe metric families. Those metrics read scenario
data through a hook and skip entirely without it, so a scenario that declines
them leaves them untestable: every assertion available is that they declined.
Implementing both here is what lets `tests/metrics` score them for real, and it
doubles as a worked example of the smallest thing each hook can return.

Registered nowhere. Tests construct it directly.
"""

from pathlib import Path
from typing import Any

from glossogen.evaluation.metric_core.protocol_probe_config import ProtocolProbeConfig
from glossogen.evaluation.metrics.communication.round_view import (
    CommunicationMessageLine,
    CommunicationRoundView,
)
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs

LINK_CHANNEL_ID = "link"
FIRST_AGENT_ID = "first_agent"
SECOND_AGENT_ID = "second_agent"
RECORD_TOOL_NAME = "record_finding"

TESTBED_DIR = Path(__file__).resolve().parent
PROBE_QUESTIONS_PATH = TESTBED_DIR / "probe_questions.json"
PROBE_PROMPTS_DIR = TESTBED_DIR / "probe_prompts"
# The question bank entry both agents answer, which is what gives the
# agent-pair similarity metric a pair to compare.
EVERYONE_ROLE_FILTER = "everyone"
SHARED_QUESTION_ID = "q_shared_protocol"

BASE_TOOLS = (
    "read_notifications",
    "read_channel",
    "send_message",
    "list_channels",
    "get_channel_members",
)


class SmokeKnobs(BaseKnobs):
    """Knobs for the smoke scenario, with a note the injection echoes back."""

    round_note: str = "proceed"
    # Off by default so the ordinary run has no postmortem phase, which is what
    # lets a test tell "no postmortem happened" apart from "one happened and
    # did not time out". The two are different measurements.
    postmortem_enabled: bool = False


class SmokeWorld(ScenarioWorld):
    """Records what the custom tool was given, per round."""

    def __init__(self) -> None:
        """Start with no recorded findings."""
        self.findings: list[tuple[int, str, str]] = []

    def record(self, *, round_number: int, agent_id: str, finding: str) -> None:
        """Store one call to the custom tool."""
        self.findings.append((round_number, agent_id, finding))

    def findings_for(self, *, round_number: int) -> list[tuple[int, str, str]]:
        """Return the findings recorded in one round."""
        return [f for f in self.findings if f[0] == round_number]


class SmokeScenario(SimulationScenario):
    """Two agents on one channel, plus a tool that records a string."""

    _agent_display_names = {FIRST_AGENT_ID: "First Agent", SECOND_AGENT_ID: "Second Agent"}
    _channel_display_names = {LINK_CHANNEL_ID: "link"}

    def __init__(self, knobs: SmokeKnobs) -> None:
        """Build the world this scenario's tool writes to."""
        self._knobs = knobs
        self._world = SmokeWorld()

    @classmethod
    def knobs_model(cls) -> type[SmokeKnobs]:
        """Return the knobs model."""
        return SmokeKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return both roles; the roster does not vary with knobs."""
        _ = knobs
        return [
            AgentRole(agent_id=FIRST_AGENT_ID, role_name="First Agent"),
            AgentRole(agent_id=SECOND_AGENT_ID, role_name="Second Agent"),
        ]

    def name(self) -> str:
        """Return the scenario identifier.

        Overridden because the base derives this from the package directory, and
        this scenario lives under ``tests`` rather than in the scenarios package.
        """
        return "smoke"

    def scenario_description(self) -> str:
        """Return the description a test asserts reached the event log."""
        return "Smoke scenario: two agents exchange findings over one channel."

    def get_knobs(self) -> SmokeKnobs:
        """Return the validated knobs."""
        return self._knobs

    def get_world(self) -> SmokeWorld:
        """Return the world the custom tool writes to."""
        return self._world

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Return both agents, each holding every base tool plus the custom one."""
        return [
            AgentConfig(
                agent_id=agent_id,
                role_name=self.get_agent_display_name(agent_id=agent_id),
                system_prompt=f"You are {agent_id}. Coordinate on #link.",
                channel_ids=[LINK_CHANNEL_ID],
                tool_names=[*BASE_TOOLS, RECORD_TOOL_NAME],
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
            for agent_id in (FIRST_AGENT_ID, SECOND_AGENT_ID)
        ]

    def get_channels(self) -> list[Channel]:
        """Return the single channel both agents share."""
        return [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=[FIRST_AGENT_ID, SECOND_AGENT_ID],
            )
        ]

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """Return the one channel that carries the conversation."""
        return [PrimaryChannel(channel_id=LINK_CHANNEL_ID, team_id=None)]

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return a round-start message naming the round, so tests can match it."""
        return (
            f"Round {round_number} for {agent_id}. "
            f"Note: {self._knobs.round_note}. Record a finding, then go idle."
        )

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Open a postmortem phase after each round when the knob is on.

        Returning text from any agent is what makes the game clock enter the
        phase at all, so this is the switch the postmortem metrics need.
        """
        _ = agent_id
        if not self._knobs.postmortem_enabled:
            return None
        return f"Round {round_number} is over. Discuss what happened."

    def get_max_postmortem_duration_seconds(self) -> float:
        """Expose the phase's wall-clock limit so a test can force a timeout."""
        return self._knobs.postmortem_duration_seconds

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return the single custom tool, which records into the world."""

        async def record_finding(ctx: ToolContext, finding: str) -> str:
            """Record a finding for this round."""
            runtime = self._runtime
            if runtime is None:
                raise RuntimeError("record_finding called before the runtime was bound")
            self._world.record(
                round_number=runtime.current_round,
                agent_id=resolve_agent_id(ctx=ctx),
                finding=finding,
            )
            return f"recorded: {finding}"

        return [
            ScenarioMcpTool(
                name=RECORD_TOOL_NAME,
                description="Record a finding for this round.",
                executor=record_finding,
            )
        ]

    def build_communication_rounds(
        self, events: list[SimulationEvent]
    ) -> list[CommunicationRoundView]:
        """Opt into the communication pipeline with one view per round that spoke.

        A scenario's job here is to pair each round's primary-channel messages
        with a description of what the agents were working from, so the judge
        scores the transcript against what the round actually wanted. There is
        no case data to describe here, so the ground-truth block reports the
        one thing this scenario does track: what the round's findings were.
        """
        by_round: dict[int, list[CommunicationMessageLine]] = {}
        for event in events:
            if not isinstance(event, MessageSent):
                continue
            if event.message.channel_id != LINK_CHANNEL_ID:
                continue
            by_round.setdefault(event.round_number, []).append(
                CommunicationMessageLine(
                    sender_agent_id=event.message.sender_agent_id,
                    channel_id=event.message.channel_id,
                    text=event.message.text,
                )
            )
        return [
            CommunicationRoundView(
                round_number=round_number,
                header=f"smoke round {round_number}",
                ground_truth_block=(
                    f"Round {round_number}: both agents share #link and may record a "
                    f"finding. Findings recorded: "
                    f"{len(self._world.findings_for(round_number=round_number))}."
                ),
                messages=messages,
            )
            for round_number, messages in sorted(by_round.items())
        ]

    def get_protocol_probe_config(self) -> ProtocolProbeConfig:
        """Opt into the probe family, pointing at this package's bank and prompts.

        `role_groups` maps a question's ``agent_role_filter`` onto the display
        names the probe matches agents by, which is why the values here are the
        role names rather than the agent ids.

        The `everyone` filter matches both agents on purpose. The agent-pair
        similarity metric groups probe rows by (question, cutoff, filter) and
        needs a group holding more than one agent, so a bank whose every
        question targets a single role leaves that metric with nothing to
        compare and it skips.
        """
        return ProtocolProbeConfig(
            questions_path=PROBE_QUESTIONS_PATH,
            prompts_dir=PROBE_PROMPTS_DIR,
            role_groups={
                FIRST_AGENT_ID: frozenset({"First Agent"}),
                SECOND_AGENT_ID: frozenset({"Second Agent"}),
                EVERYONE_ROLE_FILTER: frozenset({"First Agent", "Second Agent"}),
            },
            role_templates={
                FIRST_AGENT_ID: "first_agent_probe.jinja",
                SECOND_AGENT_ID: "second_agent_probe.jinja",
                EVERYONE_ROLE_FILTER: "everyone_probe.jinja",
            },
        )

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Pass the round when any finding was recorded in it."""
        _ = trigger
        recorded = self._world.findings_for(round_number=round_number)
        return [
            RoundResult(
                success=len(recorded) > 0,
                team_id=None,
                reason=f"{len(recorded)} finding(s) recorded",
            )
        ]
