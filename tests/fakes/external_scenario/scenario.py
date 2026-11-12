"""A scenario defined outside the built-in package, loaded through a scenario source.

``ExternalScenario`` is complete and can be built, because resolution and working
are different claims: it is constructed from its own preset and renders its prompt
from its own package, which is what the guide promises a scenario outside
glossogen can do.
"""

from pathlib import Path
from typing import Any

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.agent_config import AgentConfig, AgentRole
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.models.event_base import EventBase
from glossogen.scenario_contract.base_knobs import BaseKnobs
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.registration import scenario
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenario_contract.scenario_base import PrimaryChannel, RoundResult
from glossogen.scenario_contract.scenario_tool import ScenarioTool
from glossogen.scenario_contract.scenario_world import ScenarioWorld
from glossogen.template_renderer import TemplateRenderer
from tests.fakes.external_scenario.events import ExternalScenarioProbed
from tests.fakes.external_scenario.run_detail_extension import ExternalScenarioRunDetailExtension

PROBE_AGENT_ID = "prober"
LINK_ID = "link"


class ExternalScenarioKnobs(BaseKnobs):
    """The fake's own knobs.

    Exists because the guide says a seed belongs in the scenario's own model:
    ``BaseKnobs`` declares none, and a seed in the preset would otherwise be
    refused as an unknown knob.
    """

    seed: int


@scenario(name="external_scenario")
class ExternalScenario(SimulationScenario):
    """A complete scenario, standing in for one defined outside glossogen.

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
    def run_detail_extension(cls) -> ScenarioRunDetailExtension:
        """A message count, so an external package is shown declaring one."""
        return ExternalScenarioRunDetailExtension()

    @classmethod
    def knobs_model(cls) -> type[ExternalScenarioKnobs]:
        """Its own model, because the preset carries a seed and ``BaseKnobs`` has none."""
        return ExternalScenarioKnobs

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        """The one event this scenario declares."""
        return (ExternalScenarioProbed,)

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
                provider=Provider(default_provider),
                compaction=self._knobs.compaction,
            )
        ]

    def get_channels(self) -> list[Channel]:
        """The single link channel."""
        return [Channel(channel_id=LINK_ID, name="link", member_agent_ids=[PROBE_AGENT_ID])]

    def get_primary_channels(self) -> list[PrimaryChannel]:
        """The link is what the throughput and language metrics score."""
        return [PrimaryChannel(channel_id=LINK_ID, team_id=None, includes_direct_channels=False)]

    def get_world(self) -> ScenarioWorld:
        """Return the world."""
        return self._world

    def get_tools(self) -> list[ScenarioTool]:
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
