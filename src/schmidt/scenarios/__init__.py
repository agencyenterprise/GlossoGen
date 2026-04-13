"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing classes, used by the CLI
to look up and instantiate the requested scenario.
"""

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.broken_keyboard import BrokenKeyboardScenario
from schmidt.scenarios.car_recall import CarRecallScenario
from schmidt.scenarios.incident_response import IncidentResponseScenario
from schmidt.scenarios.persuasion_debate import PersuasionDebateScenario
from schmidt.scenarios.product_launch import ProductLaunchScenario
from schmidt.scenarios.software_procurement import SoftwareProcurementScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "broken_keyboard": BrokenKeyboardScenario,
    "incident_response": IncidentResponseScenario,
    "car_recall": CarRecallScenario,
    "product_launch": ProductLaunchScenario,
    "persuasion_debate": PersuasionDebateScenario,
    "software_procurement": SoftwareProcurementScenario,
}
