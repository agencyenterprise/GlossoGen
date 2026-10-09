"""Rebuild a run's scenario from the config the run recorded.

The config of a run older than the scenario's current knobs is missing whatever
knobs were added since, and validation rejects it. The recorded config is tried
first, then that config backfilled from each preset the scenario ships, until one
rebuilds. Only keys the run is missing are filled, so its own values always win.

Every preset is tried rather than the first because a backfill can produce a
combination a cross-field validator rejects (a run's own `yard_slot_count` merged
with a preset's `batch_size_values` in `container_yard_stacking`, for instance).
Another preset may still fit.
"""

import logging
from collections.abc import Iterator
from typing import Any

from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


def candidate_configs(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield the configs to try rebuilding from, most faithful to the run first.

    The recorded config, then it backfilled from each preset the scenario ships.
    A preset that fills nothing is skipped, since it would repeat the attempt
    just made.
    """
    yield scenario_config
    for preset_name in scenario_cls.knobs_preset_names():
        try:
            preset = scenario_cls.load_knobs_preset(preset_name=preset_name)
        except Exception:
            logger.exception("Could not read the %s preset of %s", preset_name, scenario_cls)
            continue
        merged = {**preset, **scenario_config}
        if merged == scenario_config:
            continue
        yield merged


def rebuild_recorded_scenario(
    scenario_name: str,
    scenario_config: dict[str, Any],
) -> SimulationScenario | None:
    """The scenario built from the run's recorded config, or ``None`` when nothing rebuilds it.

    ``None`` also covers a scenario that is not installed. The failure is logged
    with the last error that caused it, since a caller rendering "not known"
    otherwise gives no hint why.
    """
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        logger.info("No scenario named %s is installed, so it cannot be rebuilt", scenario_name)
        return None

    last_error: Exception | None = None
    for config in candidate_configs(scenario_cls=scenario_cls, scenario_config=scenario_config):
        try:
            return scenario_cls.create_from_recorded_config(config=config)
        except Exception as exc:
            # Held rather than logged here: a run predating a knob fails this on
            # its recorded config and succeeds on the next candidate, so logging
            # each attempt would put a stack trace in the log for every old run
            # that then resolved fine. The one that ends the loop is logged below.
            last_error = exc

    logger.info(
        "Could not rebuild %s from its recorded config or from any preset backfilled onto it",
        scenario_name,
        exc_info=last_error,
    )
    return None
