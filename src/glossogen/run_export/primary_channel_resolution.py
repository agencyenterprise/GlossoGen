"""Which of a run's channels the scenario considers primary, and whose team it is.

The message table needs this for two columns a hand-written exporter hardcodes:
whether a message was on the budgeted task channel, and which team sent it.
`get_primary_channels` is a required scenario hook, so asking the scenario is
scenario-agnostic in a way naming channel ids here would not be. The scenario is
rebuilt from the run's recorded config by `recorded_scenario_rebuild`.

When nothing rebuilds it, the two columns render empty, which says "not known"
rather than "not primary".
"""

import logging
from typing import Any, NamedTuple

from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.models.event import ChannelCreated
from glossogen.recorded_scenario_rebuild import rebuild_recorded_scenario
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


def _team_by_channel(
    scenario: SimulationScenario, created_channels: list[ChannelCreated]
) -> dict[str, str]:
    """Map each channel a primary channel scores, direct channels included, to its team id."""
    team_by_channel: dict[str, str] = {}
    for channel in scenario.get_primary_channels():
        team_id = ""
        if channel.team_id is not None:
            team_id = channel.team_id
        for channel_id in scored_channel_ids(
            primary=channel, scenario=scenario, events=created_channels
        ):
            team_by_channel[channel_id] = team_id
    return team_by_channel


def resolve_primary_channels(
    scenario_name: str,
    scenario_config: dict[str, Any],
    created_channels: list[ChannelCreated],
) -> PrimaryChannelMap:
    """Return the run's primary channels, or ``UNRESOLVED`` when nothing rebuilds it.

    ``created_channels`` are the run's ``channel_created`` events, so the direct
    channels a primary channel includes are counted as primary too.
    """
    scenario = rebuild_recorded_scenario(
        scenario_name=scenario_name,
        scenario_config=scenario_config,
    )
    if scenario is None:
        logger.info("Exporting %s messages without primary-channel or team columns", scenario_name)
        return UNRESOLVED
    return PrimaryChannelMap(
        resolved=True,
        team_by_channel=_team_by_channel(scenario=scenario, created_channels=created_channels),
    )
