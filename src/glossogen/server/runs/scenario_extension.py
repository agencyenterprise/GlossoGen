"""The run-detail extensions scenarios declare, read from the loaded scenarios.

Each scenario declares its extension through
:meth:`glossogen.scenario_contract.protocol.SimulationScenario.run_detail_extension`.
:mod:`glossogen.server.runs.detail_reader` calls the matching extension's
``build_extras`` after the generic event walk, and the app factory publishes the
extras and SSE event models of every extension in the API schema
(:mod:`glossogen.server.runs.scenario_openapi`).
"""

from glossogen.scenario_contract.loader import find_scenario_class, iter_scenario_classes
from glossogen.scenario_contract.run_detail_extension import ScenarioRunDetailExtension


def collect_scenario_extensions() -> dict[str, ScenarioRunDetailExtension]:
    """Return the extension each loadable scenario declares, skipping scenarios that declare none."""
    collected: dict[str, ScenarioRunDetailExtension] = {}
    for name, scenario_cls in iter_scenario_classes():
        extension = scenario_cls.run_detail_extension()
        if extension is not None:
            collected[name] = extension
    return collected


def scenario_extension(scenario_name: str) -> ScenarioRunDetailExtension | None:
    """Return the extension scenario ``scenario_name`` declares.

    None when the scenario declares none, or when this process cannot load it.
    """
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        return None
    return scenario_cls.run_detail_extension()
