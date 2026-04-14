"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing classes, used by the CLI
to look up and instantiate the requested scenario.
"""

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.telephone import TelephoneScenario
from schmidt.scenarios.veyru import VeyruScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "telephone": TelephoneScenario,
    "veyru": VeyruScenario,
}
