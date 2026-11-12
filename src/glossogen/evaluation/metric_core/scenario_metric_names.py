"""The metric names a scenario offers, read without running any metric.

The scenario list, the MCP listing and the REST evaluate check all ask this per
request.
"""

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.scenario_contract.protocol import SimulationScenario


def available_metric_names(scenario_cls: type[SimulationScenario]) -> list[str]:
    """Return every metric name a scenario offers: the generic ones and its own."""
    own = {metric_cls.name for metric_cls in scenario_cls.scenario_metrics()}
    return sorted(set(GENERIC_METRIC_NAMES) | own)
