"""Registry of available simulation scenarios.

Maps scenario name strings to their implementing :class:`SimulationScenario`
classes. Used by the CLI, the server, and the replace-agent flow to look up
and instantiate the requested scenario.

Lives outside ``glossogen.scenarios`` package init so importing
:mod:`glossogen.models.event` does not trigger eager loading of every
scenario's ``scenario.py`` (which would create a circular dependency since
``scenario.py`` imports from ``glossogen.models.event``). Only top-level
consumers (CLI, server) import this module.
"""

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.container_yard_stacking.scenario import ContainerYardStackingScenario
from glossogen.scenarios.drive_module_repair.scenario import DriveModuleRepairScenario
from glossogen.scenarios.hospital_bed_assignment_privacy.scenario import (
    HospitalBedAssignmentPrivacyScenario,
)
from glossogen.scenarios.orbital_anomaly.scenario import OrbitalAnomalyScenario
from glossogen.scenarios.satellite_contact_window.scenario import SatelliteContactWindowScenario
from glossogen.scenarios.spillway_release.scenario import SpillwayReleaseScenario
from glossogen.scenarios.spot_the_difference.scenario import SpotTheDifferenceScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario
from glossogen.scenarios.warehouse_robot_recovery.scenario import WarehouseRobotRecoveryScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "container_yard_stacking": ContainerYardStackingScenario,
    "drive_module_repair": DriveModuleRepairScenario,
    "hospital_bed_assignment_privacy": HospitalBedAssignmentPrivacyScenario,
    "orbital_anomaly": OrbitalAnomalyScenario,
    "satellite_contact_window": SatelliteContactWindowScenario,
    "spillway_release": SpillwayReleaseScenario,
    "spot_the_difference": SpotTheDifferenceScenario,
    "veyru": VeyruScenario,
    "warehouse_robot_recovery": WarehouseRobotRecoveryScenario,
}
