"""Look up scenario classes from the scenario registry."""

import logging

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY

logger = logging.getLogger(__name__)


def get_scenario_class(name: str) -> type[SimulationScenario]:
    """Return the scenario class registered under the given name.

    Raises ValueError if the name does not match any registered scenario.
    """
    if name not in SCENARIO_REGISTRY:
        available = ", ".join(sorted(SCENARIO_REGISTRY.keys()))
        raise ValueError(f"Unknown scenario: '{name}'. Available scenarios: {available}")
    return SCENARIO_REGISTRY[name]
