"""Look up and instantiate simulation scenarios from the scenario registry."""

import logging

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios import SCENARIO_REGISTRY

logger = logging.getLogger(__name__)


def load_scenario(name: str) -> SimulationScenario:
    """Look up a scenario by name in the registry and return a new instance.

    Raises ValueError if the name does not match any registered scenario.
    """
    if name not in SCENARIO_REGISTRY:
        available = ", ".join(sorted(SCENARIO_REGISTRY.keys()))
        raise ValueError(f"Unknown scenario: '{name}'. Available scenarios: {available}")
    logger.info("Loading scenario: %s", name)
    return SCENARIO_REGISTRY[name]()
