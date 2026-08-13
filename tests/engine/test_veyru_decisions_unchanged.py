"""Veyru has to keep deciding what it decides today, one migration step at a time.

The engine replaces veyru's mechanics in pieces. Each piece is a chance to
change a decision by accident: a budget compared with the wrong operator, a
round finalised before its outcome is recorded, an injection rendered from the
wrong case. None of those crash. They produce a run that completes and reports
different numbers, which is the failure this exists to catch.

Comparing the migrated veyru against the current one cannot be done by running
both, since only one exists at a time. So what it decides is recorded here as a
golden file, checked in, and the migration is held against it.

The file records only what `structural_equivalence` deems reproducible:
decisions in order, and each agent's own messages. Regenerate with

    GLOSSOGEN_UPDATE_BASELINE=1 uv run pytest tests/engine/test_veyru_decisions_unchanged.py

and read the diff before committing it. A regenerated baseline that silently
absorbs a behaviour change is worse than no baseline, because it looks like
coverage.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.scenarios.scenario_runtime import run_rounds
from tests.testbed.structural_equivalence import (
    decision_events,
    describe_difference,
    messages_by_sender,
)

pytestmark = pytest.mark.xdist_group("veyru")

ROUNDS = 2
UPDATE_ENV_VAR = "GLOSSOGEN_UPDATE_BASELINE"

# Both settings are recorded because they exercise different code. With the
# debrief open, the postmortem injection computes each round's outcome while the
# character counters still hold that round, and `compute_outcome_if_needed` is
# idempotent, so the round boundary only re-reads what is already stored. With
# it closed, the boundary computes the outcome for the first time, and whether
# the counters are reset before or after that becomes observable. Recording only
# the open case hides an entire class of ordering bug.
CONFIGURATIONS: dict[str, dict[str, Any]] = {
    "debrief_open": {"seed": 42, "postmortem_enabled": True},
    "debrief_closed": {
        "seed": 42,
        "postmortem_enabled": False,
        "postmortem_after_swap": False,
    },
}


def baseline_path(configuration: str) -> Path:
    """Return the golden file for one configuration."""
    return Path(__file__).parent / f"veyru_decision_baseline_{configuration}.json"


async def play_veyru(
    configuration: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[dict[str, Any]]:
    """Run veyru at the canonical seed under one configuration."""
    result = await run_rounds(
        scenario_name="veyru",
        round_count=ROUNDS,
        overrides=dict(CONFIGURATIONS[configuration]),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return result.events


def as_baseline(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Reduce a run to the part that reproduces, ready to serialise."""
    return {
        "decisions": decision_events(events),
        "messages_by_sender": messages_by_sender(events),
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
    return events


@pytest.mark.parametrize("configuration", sorted(CONFIGURATIONS))
async def test_veyru_decides_what_the_baseline_recorded(
    configuration: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The migration's contract, in one assertion."""
    events = await play_veyru(configuration, tmp_path, monkeypatch)
    path = baseline_path(configuration=configuration)

    if os.environ.get(UPDATE_ENV_VAR):
        path.write_text(json.dumps(as_baseline(events), indent=1, default=str) + "\n")
        pytest.skip(f"baseline rewritten; unset {UPDATE_ENV_VAR} and read the diff")

    assert path.exists(), f"no baseline recorded; create one with {UPDATE_ENV_VAR}=1"
    recorded = json.loads(path.read_text())

    difference = describe_difference(to_events(recorded), to_events(as_baseline(events)))

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
        "veyru_case_started",
        "simulation_ended",
    ):
        assert required in kinds, f"{required} is missing from the baseline"
    assert recorded["messages_by_sender"], "the baseline recorded no messages"
    holds_debrief = CONFIGURATIONS[configuration]["postmortem_enabled"]
    assert (
        "postmortem_started" in kinds
    ) == holds_debrief, "the baseline disagrees with the configuration about whether a debrief ran"
