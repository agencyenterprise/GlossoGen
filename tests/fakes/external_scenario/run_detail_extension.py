"""Run-detail extension for the fake external scenario.

Returned by the fake scenario's ``run_detail_extension`` hook, so a package
outside glossogen can be shown to feed the ``scenario_extras`` discriminated
union on the run-detail response the same way a built-in does.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenario_contract.run_detail_types import AgentDetail, ChannelMessage


class ExternalScenarioRunExtras(ScenarioRunExtrasBase):
    """Extras payload this fake external scenario contributes."""

    scenario_name: Literal["external_scenario"] = "external_scenario"
    message_count: int


class ExternalScenarioRunDetailExtension(ScenarioRunDetailExtension):
    """Reports how many messages the run recorded, and nothing else."""

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
