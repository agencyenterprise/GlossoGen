"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing :class:`SimulationScenario`
classes. Used by the CLI, the server, and the replace-agent flow to look up
and instantiate the requested scenario.

Lives outside ``schmidt.scenarios`` package init so importing
:mod:`schmidt.models.event` does not trigger eager loading of every
scenario's ``scenario.py`` (which would create a circular dependency since
``scenario.py`` imports from ``schmidt.models.event``). Only top-level
consumers (CLI, server) import this module.
"""

from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.container_yard_stacking.scenario import ContainerYardStackingScenario
from schmidt.scenarios.salon.scenario import SalonScenario
from schmidt.scenarios.satellite_contact_window.scenario import SatelliteContactWindowScenario
from schmidt.scenarios.veyru.scenario import VeyruScenario
from schmidt.scenarios.warehouse_robot_recovery.scenario import WarehouseRobotRecoveryScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "container_yard_stacking": ContainerYardStackingScenario,
    "salon": SalonScenario,
    "satellite_contact_window": SatelliteContactWindowScenario,
    "veyru": VeyruScenario,
    "warehouse_robot_recovery": WarehouseRobotRecoveryScenario,
}
