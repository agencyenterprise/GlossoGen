"""Each scenario has to keep deciding what it decides today, one migration step at a time.

The engine replaces veyru's mechanics in pieces. Each piece is a chance to
change a decision by accident: a budget compared with the wrong operator, a
round finalised before its outcome is recorded, an injection rendered from the
wrong case. None of those crash. They produce a run that completes and reports
different numbers, which is the failure this exists to catch.

Comparing a migrated scenario against the current one cannot be done by running
both, since only one exists at a time. So what each decides is recorded here as
a golden file, checked in, and the migration is held against it.

The file records only what `structural_equivalence` deems reproducible:
decisions in order, and each agent's own messages. Regenerate with

    GLOSSOGEN_UPDATE_BASELINE=1 uv run pytest tests/engine/test_scenario_decisions_unchanged.py

and read the diff before committing it. A regenerated baseline that silently
absorbs a behaviour change is worse than no baseline, because it looks like
coverage.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenario_registry import SCENARIO_REGISTRY
from tests.scenarios.scenario_runtime import run_rounds
from tests.testbed.structural_equivalence import (
    decision_events,
    deliveries_by_recipient,
    describe_difference,
    messages_by_sender,
)

ROUNDS = 2
UPDATE_ENV_VAR = "GLOSSOGEN_UPDATE_BASELINE"

# Everything the platform logs for any scenario. What remains in a baseline is
# the scenario's own, and a baseline holding none of those would not notice the
# scenario running a different case.
PLATFORM_EVENTS = frozenset(
    {
        "simulation_started",
        "simulation_ended",
        "agent_registered",
        "agent_connected",
        "round_advanced",
        "round_ended",
        "round_result_recorded",
        "injection_delivered",
        "postmortem_started",
        "postmortem_ended",
        "world_event_delivered",
        "channel_history_cleared",
        "channel_membership_changed",
    }
)

# One per scenario from its shipped preset, which is the configuration a reader
# assumes and the one experiments start from.
#
# Veyru carries a second with the debrief closed, because the two exercise
# different code. With it open, the postmortem injection computes each round's
# outcome while the character counters still hold that round, and
# `compute_outcome_if_needed` is idempotent, so the round boundary only re-reads
# what is stored. Closed, the boundary computes it for the first time and
# whether the counters were reset first becomes observable.
CONFIGURATIONS: dict[str, tuple[str, dict[str, Any]]] = {
    name: (name, {}) for name in sorted(SCENARIO_REGISTRY)
}
CONFIGURATIONS["veyru_debrief_closed"] = (
    "veyru",
    {"postmortem_enabled": False, "postmortem_after_swap": False},
)
# The shipped presets are single-team, so without these the two-team layouts,
# where each team runs its own link and its own debrief, are recorded nowhere.
#
# veyru is absent because two-team mode names no primary channel there, so
# nothing knows where its agents talk. That is a deliberate gap veyru documents,
# not an oversight, and closing it changes what the char and language metrics
# report for every two-team veyru run.
CONFIGURATIONS["spot_the_difference_two_teams"] = (
    "spot_the_difference",
    {"two_teams": True},
)
CONFIGURATIONS["container_yard_stacking_two_teams"] = (
    "container_yard_stacking",
    {"two_teams": True},
)


def baseline_path(configuration: str) -> Path:
    """Return the golden file for one configuration."""
    return Path(__file__).parent / "baselines" / f"{configuration}.json"


async def play(
    configuration: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, Any]]:
    """Run one configuration's scenario for the recorded number of rounds."""
    scenario_name, overrides = CONFIGURATIONS[configuration]
    result = await run_rounds(
        scenario_name=scenario_name,
        round_count=ROUNDS,
        overrides=dict(overrides),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return result.events


def as_baseline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce a run to the part that reproduces, ready to serialise."""
    return {
        "decisions": decision_events(events),
        "messages_by_sender": messages_by_sender(events),
        "deliveries_by_recipient": deliveries_by_recipient(events),
    }


def to_events(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild an event list `describe_difference` can consume from a baseline.

    The comparison takes raw event logs, so the recorded halves are turned back
    into events rather than the comparison growing a second entry point that
    could drift from the one the tests exercise.
    """
    events: list[dict[str, Any]] = list(baseline["decisions"])
    for sender, messages in baseline["messages_by_sender"].items():
        for message in messages:
            events.append(
                {
                    "event_type": "message_sent",
                    "round_number": 0,
                    "message": {**message, "sender_agent_id": sender},
                }
            )
    for recipient, deliveries in baseline["deliveries_by_recipient"].items():
        for delivered in deliveries:
            events.append({**delivered, "agent_id": recipient})
    return events


@pytest.mark.parametrize("configuration", sorted(CONFIGURATIONS))
async def test_the_scenario_decides_what_the_baseline_recorded(
    configuration: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migration's contract, in one assertion."""
    events = await play(configuration, tmp_path, monkeypatch)
    path = baseline_path(configuration=configuration)

    if os.environ.get(UPDATE_ENV_VAR):
        path.write_text(json.dumps(as_baseline(events), indent=1, default=str) + "\n")
        pytest.skip(f"baseline rewritten; unset {UPDATE_ENV_VAR} and read the diff")

    assert path.exists(), f"no baseline recorded; create one with {UPDATE_ENV_VAR}=1"
    recorded = json.loads(path.read_text())

    produced = as_baseline(events)
    difference = describe_difference(to_events(recorded), to_events(produced))
    if difference:
        # Write what this run actually decided, next to the baseline it failed
        # against, so a divergence can be diffed instead of re-guessed.
        actual_path = baseline_path(configuration=configuration).with_suffix(".actual.json")
        actual_path.write_text(json.dumps(produced, indent=1, default=str) + "\n")
        difference = f"{difference}\n\nwhat this run decided: {actual_path}"

    assert difference == "", difference


@pytest.mark.parametrize("configuration", sorted(CONFIGURATIONS))
def test_the_baseline_records_the_decisions_worth_holding(configuration: str) -> None:
    """A baseline missing the interesting events would pass against anything.

    Read off the file rather than a fresh run, so a baseline regenerated from a
    broken build fails here instead of becoming the new contract.
    """
    recorded = json.loads(baseline_path(configuration=configuration).read_text())
    kinds = {d.get("event_type") for d in recorded["decisions"]}

    for required in (
        "round_advanced",
        "round_ended",
        "round_result_recorded",
        "injection_delivered",
        "simulation_ended",
    ):
        assert required in kinds, f"{required} is missing from the baseline"
    scenario_events = kinds - PLATFORM_EVENTS
    assert scenario_events, (
        "the baseline holds no scenario-specific event, so it would not notice a "
        "scenario deciding a different case"
    )
    assert recorded["messages_by_sender"], "the baseline recorded no messages"
    _, overrides = CONFIGURATIONS[configuration]
    if overrides.get("postmortem_enabled") is False:
        assert (
            "postmortem_started" not in kinds
        ), "the configuration switches the debrief off but the baseline recorded one"
