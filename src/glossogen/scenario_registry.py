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
from glossogen.scenarios.benjamin_capacity_reservation.scenario import (
    BenjaminCapacityReservationScenario,
)
from glossogen.scenarios.benjamin_destination_release.scenario import (
    BenjaminDestinationReleaseScenario,
)
from glossogen.scenarios.benjamin_help_desk.scenario import BenjaminHelpDeskScenario
from glossogen.scenarios.benjamin_private_release.scenario import BenjaminPrivateReleaseScenario
from glossogen.scenarios.benjamin_private_allocation.scenario import (
    BenjaminPrivateAllocationScenario,
)
from glossogen.scenarios.benjamin_private_remediation.scenario import (
    BenjaminPrivateRemediationScenario,
)
from glossogen.scenarios.benjamin_release_pipeline.scenario import BenjaminReleasePipelineScenario
from glossogen.scenarios.benjamin_shadow_component.scenario import BenjaminShadowComponentScenario
from glossogen.scenarios.benjamin_shadow_tradeoff.scenario import BenjaminShadowTradeoffScenario
from glossogen.scenarios.benjamin_stewardship.scenario import BenjaminStewardshipScenario
from glossogen.scenarios.bonded_counter_association.scenario import BondedCounterAssociationScenario
from glossogen.scenarios.bonded_team_production.scenario import BondedTeamProductionScenario
from glossogen.scenarios.container_yard_stacking.scenario import ContainerYardStackingScenario
from glossogen.scenarios.drive_module_repair.scenario import DriveModuleRepairScenario
from glossogen.scenarios.hospital_bed_assignment_privacy.scenario import (
    HospitalBedAssignmentPrivacyScenario,
)
from glossogen.scenarios.joint_commitment.scenario import JointCommitmentScenario
from glossogen.scenarios.orbital_anomaly.scenario import OrbitalAnomalyScenario
from glossogen.scenarios.pledge_breach.scenario import PledgeBreachScenario
from glossogen.scenarios.repeated_trust_game.scenario import RepeatedTrustGameScenario
from glossogen.scenarios.repo_stewardship.scenario import RepoStewardshipScenario
from glossogen.scenarios.satellite_contact_window.scenario import SatelliteContactWindowScenario
from glossogen.scenarios.service_reliability.scenario import ServiceReliabilityScenario
from glossogen.scenarios.shared_reserve_commitment.scenario import SharedReserveCommitmentScenario
from glossogen.scenarios.spillway_release.scenario import SpillwayReleaseScenario
from glossogen.scenarios.spot_the_difference.scenario import SpotTheDifferenceScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario
from glossogen.scenarios.warehouse_commitment.scenario import WarehouseCommitmentScenario
from glossogen.scenarios.warehouse_robot_recovery.scenario import WarehouseRobotRecoveryScenario

SCENARIO_REGISTRY: dict[str, type[SimulationScenario]] = {
    "benjamin_capacity_reservation": BenjaminCapacityReservationScenario,
    "benjamin_help_desk": BenjaminHelpDeskScenario,
    "benjamin_destination_release": BenjaminDestinationReleaseScenario,
    "benjamin_private_release": BenjaminPrivateReleaseScenario,
    "benjamin_private_allocation": BenjaminPrivateAllocationScenario,
    "benjamin_private_remediation": BenjaminPrivateRemediationScenario,
    "benjamin_release_pipeline": BenjaminReleasePipelineScenario,
    "benjamin_shadow_component": BenjaminShadowComponentScenario,
    "benjamin_shadow_tradeoff": BenjaminShadowTradeoffScenario,
    "benjamin_stewardship": BenjaminStewardshipScenario,
    "bonded_counter_association": BondedCounterAssociationScenario,
    "bonded_team_production": BondedTeamProductionScenario,
    "container_yard_stacking": ContainerYardStackingScenario,
    "drive_module_repair": DriveModuleRepairScenario,
    "hospital_bed_assignment_privacy": HospitalBedAssignmentPrivacyScenario,
    "joint_commitment": JointCommitmentScenario,
    "orbital_anomaly": OrbitalAnomalyScenario,
    "pledge_breach": PledgeBreachScenario,
    "repeated_trust_game": RepeatedTrustGameScenario,
    "repo_stewardship": RepoStewardshipScenario,
    "satellite_contact_window": SatelliteContactWindowScenario,
    "service_reliability": ServiceReliabilityScenario,
    "shared_reserve_commitment": SharedReserveCommitmentScenario,
    "spillway_release": SpillwayReleaseScenario,
    "spot_the_difference": SpotTheDifferenceScenario,
    "veyru": VeyruScenario,
    "warehouse_robot_recovery": WarehouseRobotRecoveryScenario,
    "warehouse_commitment": WarehouseCommitmentScenario,
}
