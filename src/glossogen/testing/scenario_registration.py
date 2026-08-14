"""Assert an installed scenario resolves to the class its own package defines.

`glossogen check-scenario <name>` checks the contract, and it resolves that name
through the loader, so a scenario whose entry point never took effect fails there
by not being found at all. What it cannot tell you is that the name found
somebody else's class: a name already taken by a built-in stays with the
built-in, and the collision is only logged. `check-scenario veyru` run by the
author of a second `veyru` reports a healthy scenario, the built-in one.

That case belongs in the author's own test suite, where the class is in hand and
identity can be compared.
"""

from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_protocol import SimulationScenario


def assert_scenario_is_registered(scenario_cls: type[SimulationScenario]) -> None:
    """Assert the loader resolves ``scenario_cls.name()`` to this exact class.

    Reads installed entry-point metadata, so call it against an installed
    package rather than a source tree that was never installed.
    """
    name = scenario_cls.name()
    resolved = find_scenario_class(name=name)
    assert resolved is not None, (
        f"nothing is registered under {name!r}. Declare it in the "
        f"glossogen.scenarios.v1 entry-point group and reinstall the package."
    )
    assert resolved is scenario_cls, (
        f"{name!r} resolves to {resolved.__module__}.{resolved.__qualname__}, "
        f"not {scenario_cls.__module__}.{scenario_cls.__qualname__}. The name is "
        f"taken, and the scenario that holds it keeps it."
    )
