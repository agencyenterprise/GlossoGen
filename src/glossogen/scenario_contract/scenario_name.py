"""Validation shared by the scenario catalog, the scaffold, and run imports."""

import re

_VALID_SCENARIO_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def is_valid_scenario_name(name: str) -> bool:
    """Return whether ``name`` is safe as a module and directory component."""
    return _VALID_SCENARIO_NAME.fullmatch(name) is not None
