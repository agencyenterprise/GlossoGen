"""Resolve a finished run's primary channels from its recorded scenario config.

``SimulationScenario.get_primary_channels`` is the single source of truth for
which channels evaluators score, but it is an instance method and the
run-detail reader only has the JSONL. This rebuilds the scenario from the
config logged in ``SimulationStarted`` and asks it, the same way ``evaluate``
rebuilds a scenario to score a finished run.

Only the channel ids cross the wire. ``PrimaryChannel`` also carries the team
each channel belongs to, which is what the metric layer suffixes measurement
names with, but nothing on the other side of the API reads it.

Serving historical data is the one place where raising is the worse option: a
run recorded before its knobs model gained a required field no longer
validates, and a 500 on run-detail hides the whole run rather than one field.
Those cases log the exception and return an empty list, which the UI reports as
"this scenario declares no primary channel" instead of rendering an empty
message list under a channel name nobody ever used.
"""

import logging

from glossogen.scenario_registry import SCENARIO_REGISTRY

logger = logging.getLogger(__name__)


def resolve_primary_channel_ids(
    scenario_name: str,
    scenario_config: dict[str, object],
) -> list[str]:
    """Return the ids of the channels ``scenario_name`` scores under ``scenario_config``."""
    scenario_cls = SCENARIO_REGISTRY.get(scenario_name)
    if scenario_cls is None:
        logger.warning(
            "Run detail: %r is not a registered scenario, so it reports no primary channels",
            scenario_name,
        )
        return []
    try:
        scenario = scenario_cls.create_from_config(config=dict(scenario_config))
        channels = scenario.get_primary_channels()
    except Exception:
        logger.exception(
            "Run detail: could not rebuild scenario %r from its logged config; "
            "reporting no primary channels",
            scenario_name,
        )
        return []
    return [channel.channel_id for channel in channels]
