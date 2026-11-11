"""The run-detail extension of every loadable scenario, keyed by scenario name.

Each scenario declares its extension through
:meth:`glossogen.scenario_contract.protocol.SimulationScenario.run_detail_extension`.
:mod:`glossogen.server.runs.models` builds the ``scenario_extras`` union on
``RunDetailResponse`` from these when it is imported, and
:mod:`glossogen.server.runs.detail_reader` calls the matching extension's
``build_extras`` after the generic event walk.
"""

from glossogen.scenario_contract.loader import iter_scenario_classes
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension


def collect_scenario_extensions() -> dict[str, ScenarioRunDetailExtension]:
    """Return the extension each scenario declares, skipping scenarios that declare none."""
    collected: dict[str, ScenarioRunDetailExtension] = {}
    for name, scenario_cls in iter_scenario_classes():
        extension = scenario_cls.run_detail_extension()
        if extension is not None:
            collected[name] = extension
    return collected


SCENARIO_RUN_EXTENSIONS: dict[str, ScenarioRunDetailExtension] = collect_scenario_extensions()
