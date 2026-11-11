"""The metric names a scenario offers, read without importing any installed metric.

The scenario list, the MCP listing and the REST evaluate check all ask this per
request. Installed metrics are named from their entry-point metadata, which is
the cheaper question; whether one actually loads is asked when it runs.
"""

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.metric_entry_points import external_metric_names
from glossogen.scenario_contract.protocol import SimulationScenario


def available_metric_names(scenario_cls: type[SimulationScenario]) -> list[str]:
    """Return every metric name a scenario offers: generic, its own, and installed."""
    own = {metric_cls.name for metric_cls in scenario_cls.scenario_metrics()}
    return sorted(set(GENERIC_METRIC_NAMES) | own | set(external_metric_names()))
