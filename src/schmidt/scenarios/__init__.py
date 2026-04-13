"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing classes, used by the CLI
to look up and instantiate the requested scenario.
"""

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.car_recall import CarRecallScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "car_recall": CarRecallScenario,
}
