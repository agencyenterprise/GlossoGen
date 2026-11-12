"""Abstract base class that every simulation scenario must implement.

Defines the contract for autonomous execution mode. Each scenario specifies
its agents, channels, injections, timing parameters, and evaluation logic.
:class:`SimulationScenario` adds to :class:`glossogen.scenario_contract.scenario_base.ScenarioBase`
the hooks through which a scenario declares the parts the platform registers
for it: its own event types, its own metrics and its run-detail extension.
"""

from collections.abc import Sequence

from glossogen.models.event_base import EventBase
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension
from glossogen.scenario_contract.scenario_base import ScenarioBase


class SimulationScenario(ScenarioBase):
    """Contract that a scenario plug-in must fulfil to run in autonomous mode.

    Each concrete subclass defines the agents, channels, prompt injections,
    timing parameters, and evaluation logic that comprise a single simulation
    scenario, and declares any metrics and run-detail extension of its own.
    """

    @classmethod
    def event_types(cls) -> tuple[type[EventBase], ...]:
        """Return the event classes this scenario logs on top of the platform's own.

        A scenario with no events of its own returns ``()``, which is the default.
        """
        return ()

    @classmethod
    def scenario_metrics(cls) -> Sequence[type[Metric]]:
        """Return the metrics that apply only to this scenario's runs.

        They are offered and runnable for this scenario alongside the generic
        metrics and any installed ones, and for no other scenario. A name must not
        repeat a generic metric's. The default declares none.
        """
        return ()

    @classmethod
    def run_detail_extension(cls) -> ScenarioRunDetailExtension | None:
        """Return the extension that adds this scenario's data to the run-detail API.

        The default is None: the run-detail response carries no scenario extras.
        """
        return None
