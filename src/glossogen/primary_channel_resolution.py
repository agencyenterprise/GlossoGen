"""Resolve a finished run's primary channels from its recorded scenario config.

``SimulationScenario.get_primary_channels`` is the single source of truth for
which channels evaluators score, but it is an instance method and a finished run
only has its JSONL. This rebuilds the scenario from the config logged in
``SimulationStarted`` and asks it, the same way ``evaluate`` rebuilds a scenario
to score a finished run. The direct channels a primary channel includes, read
from the run's ``channel_created`` events, count as primary too.

Run detail reads the ordered channel ids. The message export reads the team
behind each channel and whether the scenario rebuilt at all.

The rebuild goes through ``rebuild_recorded_scenario``, which backfills the
knobs a run predates from the presets the scenario ships. A run recorded before
its knobs model gained a required field rebuilds that way instead of failing
validation.

Serving historical data is the one place where raising is the worse option: a
500 on run detail hides the whole run rather than one field. A run that no
preset rebuilds, or whose rebuilt scenario raises when asked for its primary
channels, resolves to ``UNRESOLVED``. Run detail shows that as "this scenario
declares no primary channel"; the export renders its primary-channel and team
columns empty, which says "not known" rather than "not primary".
"""

import logging
from collections.abc import Sequence
from typing import Any, NamedTuple

from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.models.event import SimulationEvent
from glossogen.recorded_scenario_rebuild import rebuild_recorded_scenario

logger = logging.getLogger(__name__)


class RecordedPrimaryChannels(NamedTuple):
    """The primary channels of one finished run, and the team each belongs to.

    ``resolved`` is False when the scenario could not be rebuilt or would not
    report its primary channels. The other two fields are then empty and say
    nothing about any channel, which is not the same as a resolved run with no
    primary channels.

    ``channel_ids`` lists each primary channel, followed by the direct channels
    it includes in sorted order, without repeats. ``team_by_channel`` maps each of
    those ids to its team id, empty string for a single-team scenario.
    """

    resolved: bool
    channel_ids: list[str]
    team_by_channel: dict[str, str]


UNRESOLVED = RecordedPrimaryChannels(resolved=False, channel_ids=[], team_by_channel={})


def resolve_recorded_primary_channels(
    scenario_name: str,
    scenario_config: dict[str, Any],
    events: Sequence[SimulationEvent],
) -> RecordedPrimaryChannels:
    """Return the channels ``scenario_name`` scores under ``scenario_config``.

    ``events`` are the run's events, of which only ``channel_created`` is read.
    Returns ``UNRESOLVED`` when nothing rebuilds the scenario or the rebuilt
    scenario raises from ``get_primary_channels``.
    """
    scenario = rebuild_recorded_scenario(
        scenario_name=scenario_name, scenario_config=dict(scenario_config)
    )
    if scenario is None:
        return UNRESOLVED
    try:
        channels = scenario.get_primary_channels()
    except Exception:
        logger.exception(
            "Scenario %r rebuilt but would not report its primary channels", scenario_name
        )
        return UNRESOLVED
    channel_ids: list[str] = []
    team_by_channel: dict[str, str] = {}
    for channel in channels:
        team_id = ""
        if channel.team_id is not None:
            team_id = channel.team_id
        included = scored_channel_ids(primary=channel, scenario=scenario, events=events)
        channel_ids.append(channel.channel_id)
        channel_ids.extend(sorted(included - {channel.channel_id}))
        for channel_id in included:
            team_by_channel[channel_id] = team_id
    return RecordedPrimaryChannels(
        resolved=True,
        channel_ids=list(dict.fromkeys(channel_ids)),
        team_by_channel=team_by_channel,
    )
