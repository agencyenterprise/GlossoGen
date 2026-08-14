"""The scenario classes an entry point would name.

``ExternalScenario`` is complete and can be built, because resolution and working
are different claims: it is constructed from its own preset and renders its prompt
from its own package, which is what the guide promises an out-of-tree scenario can
do. The others exist to be refused, and are left abstract because the loader
checks what a class *is* before anything is constructed.

A scenario built against another contract version needs no class of its own: the
version lives in the entry-point group, so a skewed plug-in is this same class
declared under a different group.
"""

from pathlib import Path
from typing import Any

from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.runtime.scenario_mcp_tool import ScenarioMcpTool
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, RoundResult, SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs
from glossogen.template_renderer import TemplateRenderer

PROBE_AGENT_ID = "prober"
LINK_ID = "link"


class ExternalScenarioKnobs(BaseKnobs):
    """The fake's own knobs.

    Exists because the guide says a seed belongs in the scenario's own model:
    ``BaseKnobs`` declares none, and ``extra="ignore"`` means a seed in the preset
    would otherwise be dropped without a word.
    """

    seed: int


class ExternalScenario(SimulationScenario):
    """A complete scenario, standing in for one shipped by another distribution.

    Every abstract method is implemented, so this can be constructed from its own
    preset and asked for its agents. That is the part resolution alone does not
    prove: the guide promises prompts resolve relative to the scenario's package,
    and rendering one from here is what checks it.
    """

    def __init__(self, knobs: ExternalScenarioKnobs) -> None:
        self._knobs = knobs
        self._renderer = TemplateRenderer(prompts_dirs=[Path(__file__).parent / "prompts"])
        self._world = ScenarioWorld(
            postmortem_channel_ids=frozenset(),
            postmortem_globally_disabled=False,
        )

    @classmethod
    def knobs_model(cls) -> type[ExternalScenarioKnobs]:
        """Its own model, because the preset carries a seed and ``BaseKnobs`` has none."""
        return ExternalScenarioKnobs

    @classmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """One role, under every configuration."""
        _ = knobs
        return [AgentRole(agent_id=PROBE_AGENT_ID, role_name="Prober")]

    def get_knobs(self) -> BaseKnobs:
        """Return the validated knobs."""
        return self._knobs

    def scenario_description(self) -> str:
        """One line, as the run list shows it."""
        return "One agent says something short on a link."

    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
        """Build the one agent, rendering its prompt from this package."""
        return [
            AgentConfig(
                agent_id=PROBE_AGENT_ID,
                role_name="Prober",
                system_prompt=self._renderer.render(
                    template_name="probe_system.jinja",
                    template_variables={
                        "channels": [
                            ChannelTemplateEntry(display_name="the link", channel_id=LINK_ID)
                        ]
                    },
                ),
                channel_ids=[LINK_ID],
                tool_names=[],
                model=default_model,
                provider=default_provider,
                max_tokens=self._knobs.agent_max_tokens,
                compaction=self._knobs.compaction,
            )
        ]

    def get_channels(self) -> list[Channel]:
        """The single link channel."""
        return [Channel(channel_id=LINK_ID, name="link", member_agent_ids=[PROBE_AGENT_ID])]

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """The link is what the throughput and language metrics score."""
        return [PrimaryChannel(channel_id=LINK_ID, team_id=None)]

    def get_world(self) -> ScenarioWorld:
        """Return the world."""
        return self._world

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """No scenario tools."""
        return []

    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Nudge the one agent each round."""
        _ = agent_id
        return f"Round {round_number}: say something short."

    def judge_round_result(self, round_number: int, trigger: str) -> list[RoundResult]:
        """Always succeed; what is under test is construction, not scoring."""
        _ = trigger
        return [RoundResult(success=True, team_id=None, reason=f"round {round_number} ran")]


class SecondExternalScenario(SimulationScenario):
    """A second class, for the case of two distributions claiming one name."""


class RenamedScenario(SimulationScenario):
    """Answers to a name of its own, to be caught when it is registered under another.

    A scenario may legitimately override ``name()``; what it may not do is
    disagree with the name it is registered under, because run directories are
    named after ``name()`` and every later command looks a run up by the
    registered name.
    """

    @classmethod
    def name(cls) -> str:
        """Report a name deliberately unlike any entry-point name used in tests."""
        return "some_other_name"


class BrokenImportScenario(SimulationScenario):
    """Never reached: the entry point for this one names a module that raises."""


NOT_A_SCENARIO = "a string, which is not a SimulationScenario subclass"
"""What an entry point pointing at the wrong object resolves to."""
