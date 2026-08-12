"""The structural log has to reproduce, or two implementations cannot be compared.

Replacing a hand-written scenario with a generated one is only safe if the two
can be shown to decide the same things. That comparison is worthless unless the
thing being compared is stable for a single implementation first, which is what
this pins.

It guards the blocklist in `structural_equivalence` as much as the platform: if
some event that varies run to run is later treated as structural, this fails and
names it, rather than the comparison quietly becoming flaky for whoever is
mid-migration.
"""

from pathlib import Path
from typing import Any

import pytest

from tests.scenarios.scenario_runtime import run_rounds
from tests.testbed.structural_equivalence import describe_difference, structural_events

pytestmark = pytest.mark.xdist_group("veyru")

ROUNDS = 2


async def play_veyru(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Run veyru at the canonical seed with its debrief open."""
    result = await run_rounds(
        scenario_name="veyru",
        round_count=ROUNDS,
        overrides={"seed": 42, "postmortem_enabled": True},
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    return result.events


async def test_two_identical_runs_decide_the_same_things(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same code, same seed, same decisions, down to the field."""
    first = await play_veyru(tmp_path / "first", monkeypatch)
    second = await play_veyru(tmp_path / "second", monkeypatch)

    difference = describe_difference(first, second)

    assert difference == "", difference


async def test_the_structural_log_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocklist that swallowed everything would make the comparison vacuous.

    Without this, filtering out one event type too many leaves an equivalence
    test that passes against any implementation at all.
    """
    events = await play_veyru(tmp_path / "only", monkeypatch)

    structural = structural_events(events)
    kinds = {e.get("event_type") for e in structural}

    assert len(structural) > 20, f"only {len(structural)} structural events survived the filter"
    for required in (
        "round_advanced",
        "round_ended",
        "round_result_recorded",
        "injection_delivered",
        "message_sent",
        "veyru_case_started",
        "simulation_ended",
    ):
        assert required in kinds, f"{required} was filtered out of the structural log"
