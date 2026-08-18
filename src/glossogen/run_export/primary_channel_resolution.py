"""Which of a run's channels the scenario considers primary, and whose team it is.

The message table needs this for two columns a hand-written exporter hardcodes:
whether a message was on the budgeted task channel, and which team sent it.
`get_primary_channels` is a required scenario hook, so asking the scenario is
scenario-agnostic in a way naming channel ids here would not be.

Answering needs the scenario rebuilt from the config the run recorded, and the
config of a run older than the scenario's current knobs is missing whatever knobs
were added since. Validation rejects it, and rebuilding fails on knobs that have
nothing to do with channels: 50 of the 52 `container_yard_stacking` runs here
fail on `batch_size_values` and `batch_size_weights`, and every one of them is a
single-team run on `link`.

So the recorded config is tried first, then that config backfilled from each
preset the scenario ships, until one rebuilds. Only keys the run is missing are
filled, so its own values always win and a knob that does move a channel id stays
honest. Trying every preset rather than the first matters because a backfill can
produce a combination the scenario rejects: two runs here merge their own
`yard_slot_count` with a preset's `batch_size_values` and trip
`yard_slot_count must be >= 2 * max(batch_size_values)`, which is a cross-field
validator saying that configuration never existed. Another preset may still fit.

When nothing fits, the two columns render empty, which says "not known" rather
than "not primary", and the failure is logged with the last error that caused it.
A generic "could not rebuild" is unhelpful precisely when a run comes back with
those columns empty.
"""

import logging
from collections.abc import Iterator
from typing import Any, NamedTuple

from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class PrimaryChannelMap(NamedTuple):
    """The primary channels of one run, and the team each belongs to.

    ``resolved`` is False when the scenario could not be rebuilt, in which case
    ``team_by_channel`` is empty and says nothing about any channel.
    ``team_by_channel`` maps a primary channel id to its team id, empty string
    for a single-team scenario.
    """

    resolved: bool
    team_by_channel: dict[str, str]


UNRESOLVED = PrimaryChannelMap(resolved=False, team_by_channel={})


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


def _team_by_channel(scenario: SimulationScenario) -> dict[str, str]:
    """Map each of the scenario's primary channel ids to its team id."""
    team_by_channel: dict[str, str] = {}
    for channel in scenario.get_primary_channels():
        team_id = ""
        if channel.team_id is not None:
            team_id = channel.team_id
        team_by_channel[channel.channel_id] = team_id
    return team_by_channel


def resolve_primary_channels(
    scenario_name: str,
    scenario_config: dict[str, Any],
) -> PrimaryChannelMap:
    """Return the run's primary channels, or ``UNRESOLVED`` when nothing rebuilds it."""
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        logger.info(
            "No scenario named %s is installed, so its messages carry no primary channel",
            scenario_name,
        )
        return UNRESOLVED

    last_error: Exception | None = None
    for config in candidate_configs(scenario_cls=scenario_cls, scenario_config=scenario_config):
        try:
            scenario = scenario_cls.create_from_config(config=config)
            team_by_channel = _team_by_channel(scenario=scenario)
        except Exception as exc:
            # Held rather than logged here: a run predating a knob fails this on
            # its recorded config and succeeds on the next candidate, so logging
            # each attempt would put a stack trace in the log for every old run
            # that then resolved fine. The one that ends the loop is logged below.
            last_error = exc
            continue
        return PrimaryChannelMap(resolved=True, team_by_channel=team_by_channel)

    logger.info(
        "Could not rebuild %s from its recorded config or from any preset backfilled onto it; "
        "exporting its messages without primary-channel or team columns",
        scenario_name,
        exc_info=last_error,
    )
    return UNRESOLVED
