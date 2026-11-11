"""The class the package's ``__init__`` re-exports."""

from glossogen.scenario_contract.protocol import SimulationScenario


class ReexportedScenario(SimulationScenario):
    """Defined here, re-exported one level up. Refused when named via the package."""
