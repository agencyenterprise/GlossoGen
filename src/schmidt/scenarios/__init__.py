"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing classes, used by the CLI
to look up and instantiate the requested scenario.
"""

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.car_recall import CarRecallScenario
from schmidt.scenarios.incident_response import IncidentResponseScenario
from schmidt.scenarios.persuasion_debate import PersuasionDebateScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "incident_response": IncidentResponseScenario,
    "car_recall": CarRecallScenario,
    "persuasion_debate": PersuasionDebateScenario,
}
