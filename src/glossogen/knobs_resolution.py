"""Resolve what `--config` names into the knobs a run starts from.

A scenario ships its presets inside its own package, so a path to one is only
typeable by someone who can see that package. From a checkout that is
`src/glossogen/scenarios/<name>/knobs_default.json`; from an installed
distribution it is a path into `site-packages`, which nobody should have to
write. Scenarios already publish their presets by name for the API and the MCP
tools, so the CLI resolves a name too, and both layouts spell the same command.

A file still wins when the argument is one, which is how an experiment keeps its
own knobs JSON outside any package.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple

import orjson

from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

DEFAULT_PRESET_NAME = "knobs_default"
"""The preset a scenario is run with when `--config` is not given."""


class ResolvedKnobs(NamedTuple):
    """The knobs a run starts from, and where they came from.

    ``source`` is for the log: a run whose configuration was chosen rather than
    stated should say which preset it picked.
    """

    config: dict[str, Any]
    source: str


def resolve_knobs_config(
    scenario_cls: type[SimulationScenario],
    requested: str | None,
) -> ResolvedKnobs:
    """Return the knobs for ``requested``, a preset name, a file, or nothing.

    Omitting it takes the scenario's canonical preset, which is what its own
    documentation calls the default. A scenario shipping none resolves to an
    empty config, leaving every knob to the `key=value` overrides.

    Raises ``SystemExit`` when the argument is neither a file nor a preset the
    scenario ships, naming the ones it does.
    """
    if requested is None:
        return _canonical_preset(scenario_cls=scenario_cls)

    path = Path(requested)
    if path.is_file():
        return ResolvedKnobs(config=orjson.loads(path.read_bytes()), source=str(path))

    available = scenario_cls.knobs_preset_names()
    name = requested.removesuffix(".json")
    if name in available:
        return ResolvedKnobs(
            config=scenario_cls.load_knobs_preset(preset_name=name),
            source=f"preset {name!r}",
        )

    raise SystemExit(
        f"--config {requested!r} is neither a readable file nor a preset "
        f"{scenario_cls.name()} ships. Its presets: {', '.join(available)}."
    )


def _canonical_preset(scenario_cls: type[SimulationScenario]) -> ResolvedKnobs:
    """Return the scenario's default preset, or an empty config when it has none."""
    if DEFAULT_PRESET_NAME not in scenario_cls.knobs_preset_names():
        return ResolvedKnobs(config={}, source="no preset")
    return ResolvedKnobs(
        config=scenario_cls.load_knobs_preset(preset_name=DEFAULT_PRESET_NAME),
        source=f"preset {DEFAULT_PRESET_NAME!r}",
    )
