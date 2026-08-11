"""A small scenario used only by tests.

Real scenarios carry domain rules that muddy an assertion about the platform. A
failing test should say the platform broke, not that a Veyru was mis-stabilised.
This one has two agents, one channel, and a custom tool that records whatever it
is handed.

Registered nowhere. Tests construct it directly.
"""

from typing import Any

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool, ToolContext, resolve_agent_id
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs

LINK_CHANNEL_ID = "link"
FIRST_AGENT_ID = "first_agent"
SECOND_AGENT_ID = "second_agent"
RECORD_TOOL_NAME = "record_finding"

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
