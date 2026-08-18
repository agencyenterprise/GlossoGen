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

So a config that will not validate is backfilled from a preset the scenario
ships, filling only the keys it is missing. The run's own values win wherever it
has them, which keeps a knob that does move a channel id honest, and the
backfill only ever supplies knobs the run predates.

Backfilling stops there rather than trying harder. Mixing a run's values with a
preset's can produce a combination the scenario rejects outright, which is a
cross-field validator saying this configuration never existed: two runs here
merge their own `yard_slot_count` with the preset's `batch_size_values` and trip
`yard_slot_count must be >= 2 * max(batch_size_values)`. Reading channels off a
config the scenario calls impossible is worse than not reading them, so the two
columns render empty, which says "not known" rather than "not primary".
"""

import logging
from typing import Any, NamedTuple

from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_protocol import PrimaryChannel, SimulationScenario

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


def backfilled_config(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the config with knobs it predates filled in from a preset, or None.

    Presets are tried in the order the scenario lists them, since a scenario is
    free to ship none under any particular name and only one has to validate.
    """
    for preset_name in scenario_cls.knobs_preset_names():
        try:
            preset = scenario_cls.load_knobs_preset(preset_name=preset_name)
        except Exception:
            logger.exception("Could not read the %s preset of %s", preset_name, scenario_cls)
            continue
        merged = {**preset, **scenario_config}
        if merged == scenario_config:
            continue
        return merged
    return None


def _primary_channels_of(
    scenario_cls: type[SimulationScenario],
    scenario_config: dict[str, Any],
) -> list[PrimaryChannel] | None:
    """Rebuild the scenario and ask it for its primary channels, or None if it will not."""
    try:
        scenario = scenario_cls.create_from_config(config=scenario_config)
        return scenario.get_primary_channels()
    except Exception:
        return None


def resolve_primary_channels(
    scenario_name: str,
    scenario_config: dict[str, Any],
) -> PrimaryChannelMap:
    """Return the run's primary channels, or ``UNRESOLVED`` when the scenario will not rebuild."""
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        logger.info(
            "No scenario named %s is installed, so its messages carry no primary channel",
            scenario_name,
        )
        return UNRESOLVED

    channels = _primary_channels_of(scenario_cls=scenario_cls, scenario_config=scenario_config)
    if channels is None:
        backfilled = backfilled_config(
            scenario_cls=scenario_cls,
            scenario_config=scenario_config,
        )
        if backfilled is not None:
            channels = _primary_channels_of(
                scenario_cls=scenario_cls,
                scenario_config=backfilled,
            )
    if channels is None:
        logger.info(
            "Could not rebuild %s from its recorded config, even with preset defaults for the "
            "knobs it predates; exporting its messages without primary-channel or team columns",
            scenario_name,
        )
        return UNRESOLVED

    team_by_channel: dict[str, str] = {}
    for channel in channels:
        team_id = ""
        if channel.team_id is not None:
            team_id = channel.team_id
        team_by_channel[channel.channel_id] = team_id
    return PrimaryChannelMap(resolved=True, team_by_channel=team_by_channel)
