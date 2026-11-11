"""Which channels a finished run's scenario scores, read back from its recorded config.

Run detail reads the ordered channel ids and the message export reads the team
behind each channel, both from one ``resolve_recorded_primary_channels`` call.
Real runs here mostly predate the scenario's latest knobs, so most of these
cases are about a recorded config that no longer validates as it stands.
"""

import logging
from importlib.metadata import EntryPoint

import pytest

from glossogen.models.event import ChannelCreated
from glossogen.scenario_contract import entry_points
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenario_contract.primary_channel_resolution import (
    UNRESOLVED,
    resolve_recorded_primary_channels,
)
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.recorded_scenario_rebuild import candidate_configs
from tests.fakes.installed_entry_points import declare_in_groups

# --- resolving the primary channel across knob-schema drift ---------------------


def test_a_config_predating_a_new_knob_still_resolves_its_primary_channel() -> None:
    """The common case on real data: 50 of 52 container_yard runs here predate two knobs.

    Neither knob has anything to do with which channel is primary, so failing to
    resolve would empty a column for a whole scenario over an unrelated field.
    """
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}

    resolved = resolve_recorded_primary_channels(
        scenario_name="veyru", scenario_config=aged, events=[]
    )

    assert resolved.resolved
    assert resolved.team_by_channel == {"link": ""}


def test_a_run_predating_a_knob_still_reports_its_primary_channels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A recorded config lacks whatever knobs the scenario gained after the run.

    `rebuild_recorded_scenario` backfills those from the presets the scenario
    ships, so the run still reports the channels its evaluators scored. Resolving
    the config directly instead would fail validation the first time anyone adds
    a required knob, and every run recorded before it would quietly degrade to no
    primary channels at all.
    """
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    declared = resolve_recorded_primary_channels(
        scenario_name="veyru", scenario_config=config, events=[]
    ).channel_ids
    assert declared, "veyru declares primary channels, so the comparison below means something"

    required = next(
        name
        for name, field in scenario_cls.knobs_model().model_fields.items()
        if field.is_required() and name in config
    )
    predating = {key: value for key, value in config.items() if key != required}

    with caplog.at_level(logging.ERROR):
        resolved = resolve_recorded_primary_channels(
            scenario_name="veyru", scenario_config=predating, events=[]
        ).channel_ids

    assert resolved == declared, f"a run recorded before {required!r} reports the same channels"
    assert caplog.text == "", "a knob added after the run is not an error"


def test_the_recorded_config_is_tried_before_any_preset_fills_it() -> None:
    """A run that rebuilds on its own config must never be read through a preset's values."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")

    [first, *_] = candidate_configs(scenario_cls=scenario_cls, scenario_config=full)

    assert first == full


def test_the_run_own_values_win_over_the_preset_it_is_filled_from() -> None:
    """Backfilling supplies only what a run predates; anything it recorded is its own."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}
    aged["round_count"] = 3

    [_, backfilled, *_] = candidate_configs(scenario_cls=scenario_cls, scenario_config=aged)

    assert backfilled["round_count"] == 3
    assert "easy_round_numbers" in backfilled


def test_every_preset_is_offered_not_only_the_first() -> None:
    """One backfill can trip a cross-field validator while another still fits."""
    scenario_cls = get_scenario_class(name="veyru")
    full = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    aged = {key: value for key, value in full.items() if key != "easy_round_numbers"}

    candidates = list(candidate_configs(scenario_cls=scenario_cls, scenario_config=aged))

    # The recorded config, plus a backfill from each preset that fills something.
    assert len(candidates) > 2
    assert len(scenario_cls.knobs_preset_names()) > 1


# --- what a resolved run reports --------------------------------------------------


def test_a_two_team_scenario_names_the_team_behind_each_channel() -> None:
    """The team dimension a Measurement has no field for is known here from the channel."""
    scenario_cls = get_scenario_class(name="spot_the_difference")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")

    resolved = resolve_recorded_primary_channels(
        scenario_name="spot_the_difference", scenario_config=config, events=[]
    )

    assert resolved.resolved
    assert sorted(resolved.team_by_channel.items()) == [("link_a", "team_a"), ("link_b", "team_b")]


def channel_created(channel_id: str, member_agent_ids: list[str]) -> ChannelCreated:
    """A ``channel_created`` event, as a direct channel opening mid-run writes one."""
    return ChannelCreated(
        round_number=1, channel_id=channel_id, name=channel_id, member_agent_ids=member_agent_ids
    )


def test_the_direct_channels_a_primary_channel_includes_follow_it_in_order() -> None:
    """Run detail lists the primary channel first, then its direct channels sorted.

    A direct channel with a member outside the primary channel is not scored, so
    it is in neither the ids nor the team map.
    """
    scenario_cls = get_scenario_class(name="textcraft_shared_workspace")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    events = [
        channel_created(
            channel_id="dm:crafter_2+crafter_3", member_agent_ids=["crafter_2", "crafter_3"]
        ),
        channel_created(
            channel_id="dm:crafter_1+crafter_2", member_agent_ids=["crafter_1", "crafter_2"]
        ),
        channel_created(
            channel_id="dm:crafter_1+outsider", member_agent_ids=["crafter_1", "outsider"]
        ),
    ]

    resolved = resolve_recorded_primary_channels(
        scenario_name="textcraft_shared_workspace", scenario_config=config, events=events
    )

    assert resolved.channel_ids == [
        "workspace",
        "dm:crafter_1+crafter_2",
        "dm:crafter_2+crafter_3",
    ]
    assert resolved.team_by_channel == {channel_id: "" for channel_id in resolved.channel_ids}


# --- runs nothing can resolve ------------------------------------------------------


def test_a_scenario_that_is_not_installed_resolves_to_nothing() -> None:
    """Runs of a scenario since removed are still exported, without those columns."""
    resolved = resolve_recorded_primary_channels(
        scenario_name="a_scenario_nobody_shipped",
        scenario_config={},
        events=[],
    )

    assert not resolved.resolved
    assert resolved.channel_ids == []
    assert resolved.team_by_channel == {}


def test_a_tolerant_caller_degrades_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through the function the run-detail endpoint actually calls.

    A plug-in whose entry point names a class the package does not define makes
    the loader answer None, and the run resolves to nothing rather than raising.
    """
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            entry_points.SCENARIO_ENTRY_POINT_GROUP: [
                EntryPoint(
                    name="misdeclared",
                    value="tests.fakes.external_scenario.scenario:RenamedScenario",
                    group=entry_points.SCENARIO_ENTRY_POINT_GROUP,
                )
            ]
        },
    )

    resolved = resolve_recorded_primary_channels(
        scenario_name="misdeclared", scenario_config={}, events=[]
    )

    assert resolved == UNRESOLVED
    assert resolved.channel_ids == []


def test_a_scenario_that_raises_for_its_primary_channels_is_unresolved(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 500 on run detail would hide the whole run, so the error is logged instead.

    Unresolved, not resolved-with-no-channels: the export renders its columns
    empty, which reads as "not known".
    """
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")

    def refuse(_scenario: SimulationScenario) -> list[object]:
        raise RuntimeError("no primary channels today")

    monkeypatch.setattr(target=scenario_cls, name="get_primary_channels", value=refuse)

    with caplog.at_level(logging.ERROR):
        resolved = resolve_recorded_primary_channels(
            scenario_name="veyru", scenario_config=config, events=[]
        )

    assert resolved == UNRESOLVED
    assert "no primary channels today" in caplog.text
