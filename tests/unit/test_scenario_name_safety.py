"""External scenario names are safe run-directory components."""

from importlib.metadata import EntryPoint

import pytest

from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_loader import check_entry_point_declaration
from tests.fakes.external_scenario.scenario import ExternalScenario


@pytest.mark.parametrize("name", ["../escape", "nested/name", "nested\\name", ".hidden", "Caps"])
def test_scenario_entry_point_rejects_unsafe_names(name: str) -> None:
    """Scenario names become run-directory and zip path components."""
    entry_point = EntryPoint(
        name=name,
        value="tests.fakes.external_scenario.scenario:ExternalScenario",
        group=SCENARIO_ENTRY_POINT_GROUP,
    )

    with pytest.raises(ValueError, match="invalid name"):
        check_entry_point_declaration(
            name=name,
            entry_point=entry_point,
            loaded=ExternalScenario,
        )
