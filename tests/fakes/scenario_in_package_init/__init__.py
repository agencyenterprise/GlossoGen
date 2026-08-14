"""A scenario package laid out the way glossogen refuses: the class in ``__init__``.

Exists to be rejected. Event discovery finds the package an entry point names by
string, because it runs while ``glossogen.models.event`` is mid-import and may not
import anything; telling a package from a module requires an import, so a class
here would be misread as living in the parent package and its ``events`` module
would look absent.

The sibling ``tests/fakes/external_scenario`` is the correct shape, with an empty
``__init__`` and the class in ``scenario.py``.
"""

from glossogen.scenario_protocol import SimulationScenario


class ScenarioInPackageInit(SimulationScenario):
    """Declared in the package's own ``__init__``, which the loader refuses."""
