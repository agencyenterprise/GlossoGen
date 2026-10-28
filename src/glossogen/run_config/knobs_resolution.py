"""Resolve what `--config` and `--knobs` name into scenario knobs.

A scenario ships its presets inside its own package, so a path to one is only
typeable by someone who can see that package. From a checkout that is
`src/glossogen/scenarios/<name>/knobs_default.json`; from an installed
distribution it is a path into `site-packages`, which nobody should have to
write. Scenarios already publish their presets by name for the API and the MCP
tools, so the CLI resolves a name too, and both layouts spell the same command.

A file still wins when the argument is one, which is how an experiment keeps its
own knobs JSON outside any package.

Neither flag falls back to a preset of its own accord. `--config` is required, so
a run's configuration is stated rather than inferred: the JSONL records what a
run was launched with, and a configuration nobody chose is one nobody can
account for later.
"""

import logging
from pathlib import Path
from typing import Any, NamedTuple, cast

import orjson

from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class ResolvedKnobs(NamedTuple):
    """The knobs a run starts from, and where they came from.

    ``source`` is for the log, so a run says which preset or file it read.
    """

    config: dict[str, Any]
    source: str


def resolve_knobs_config(
    scenario_cls: type[SimulationScenario],
    requested: str,
) -> ResolvedKnobs:
    """Return the knobs `--config` names, a preset or a file.

    Raises ``SystemExit`` when the argument is neither a file nor a preset the
    scenario ships, naming the ones it does.
    """
    return _resolve_file_or_preset(scenario_cls=scenario_cls, requested=requested, flag="--config")


def resolve_knobs_overrides(
    scenario_cls: type[SimulationScenario],
    requested: str | None,
) -> ResolvedKnobs | None:
    """Return the overrides `--knobs` names, or None when it was not given.

    Same vocabulary as ``--config``, a file or a preset name, so one rule covers
    both flags. What differs is that this one is optional: no overrides is a
    resumed run's normal state.

    A preset used this way replaces every field it declares, which is what a
    whole-preset JSON file passed here has always done.
    """
    if requested is None:
        return None
    return _resolve_file_or_preset(scenario_cls=scenario_cls, requested=requested, flag="--knobs")


def _resolve_file_or_preset(
    scenario_cls: type[SimulationScenario],
    requested: str,
    flag: str,
) -> ResolvedKnobs:
    """Read ``requested`` as a file if it is one, else as a preset name."""
    path = Path(requested)
    if path.is_file():
        return ResolvedKnobs(
            config=_require_object(payload=orjson.loads(path.read_bytes()), source=str(path)),
            source=str(path),
        )

    available = scenario_cls.knobs_preset_names()
    name = requested.removesuffix(".json")
    if name in available:
        return ResolvedKnobs(
            config=scenario_cls.load_knobs_preset(preset_name=name),
            source=f"preset {name!r}",
        )

    raise SystemExit(
        f"{flag} {requested!r} is neither a readable file nor a preset "
        f"{scenario_cls.name()} ships. Its presets: {', '.join(available)}."
    )


def _require_object(payload: Any, source: str) -> dict[str, Any]:
    """Return the payload as a knobs mapping, or refuse it by name."""
    if not isinstance(payload, dict):
        raise SystemExit(f"{source} must contain a JSON object of scenario knobs.")
    return {str(key): value for key, value in cast(dict[Any, Any], payload).items()}
