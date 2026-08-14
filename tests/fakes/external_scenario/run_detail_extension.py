"""Run-detail extension for the fake external scenario.

The second submodule ``import_scenario_submodules`` is called with, and the one
that feeds the ``scenario_extras`` discriminated union on the run-detail
response. Present so discovery of it can be tested for a package outside
glossogen, which the guide promises works the same way as ``events``.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.server.runs.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.runs.scenario_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)


class ExternalScenarioRunExtras(ScenarioRunExtrasBase):
    """Extras payload this fake external scenario contributes."""

    scenario_name: Literal["external_scenario"] = "external_scenario"
    message_count: int


class ExternalScenarioRunDetailExtension(ScenarioRunDetailExtension):
    """Reports how many messages the run recorded, and nothing else."""

    scenario_name: ClassVar[str] = "external_scenario"
    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = ExternalScenarioRunExtras
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> ScenarioRunExtrasBase:
        """Count the run's messages."""
        _ = events, agents_by_id
        return ExternalScenarioRunExtras(message_count=len(messages))
