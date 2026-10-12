"""What ``launch_simulation`` refuses before it starts a subprocess.

MCP's ``start_run`` shows the caller a ``ValueError``'s message; anything else
reaches it as an opaque error, or, for a flag argparse rejects, as a launch
that reported success and then exited.
"""

from pathlib import Path

import pytest

from glossogen.scenario_loader import get_scenario_class
from glossogen.server.run_launcher import launch_simulation


def launch(tmp_path: Path, harness: str, knobs: dict[str, object]) -> None:
    launch_simulation(
        scenario_name="veyru",
        model="claude-sonnet-4-6",
        provider="anthropic",
        harness=harness,
        scenario_cls=get_scenario_class(name="veyru"),
        knobs=knobs,
        runs_dir=tmp_path,
        group_slug="local",
    )


def veyru_knobs() -> dict[str, object]:
    return dict(get_scenario_class(name="veyru").load_knobs_preset(preset_name="knobs_default"))


def test_an_unknown_run_harness_is_refused_even_when_every_seat_names_its_own(
    tmp_path: Path,
) -> None:
    knobs = veyru_knobs()
    knobs["model_overrides"] = {
        "field_observer": {"model": "claude-sonnet-4-6", "harness": "pydantic-ai"},
        "stabilization_engineer": {"model": "claude-sonnet-4-6", "harness": "pydantic-ai"},
    }
    with pytest.raises(ValueError, match="Unknown harness: 'no-such-harness'"):
        launch(tmp_path=tmp_path, harness="no-such-harness", knobs=knobs)


def test_an_unknown_harness_in_model_overrides_is_a_value_error(tmp_path: Path) -> None:
    knobs = veyru_knobs()
    knobs["model_overrides"] = {"field_observer": {"harness": "no-such-harness"}}
    with pytest.raises(ValueError, match="agents.field_observer.harness"):
        launch(tmp_path=tmp_path, harness="pydantic-ai", knobs=knobs)
