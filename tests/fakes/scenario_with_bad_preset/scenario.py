"""A scenario whose only job is to ship an unparseable preset."""

from glossogen.scenario_protocol import SimulationScenario


class ScenarioWithBadPreset(SimulationScenario):
    """Never run; only its preset is read."""
