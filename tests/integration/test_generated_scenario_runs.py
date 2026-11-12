"""A generated scenario folder runs, not just parses.

`new-scenario` promises a scenario that works before anything is edited, and a
template that only looks right is worse than none: the author would debug their
own first change against a broken starting point.

So this generates one into an empty project, loads it the way `glossogen` does
from that project, through the scan of the project directory, and puts it
through the same two gates the command's next steps tell its author to run.
Nothing is installed, no LLM is called, and no clock is waited on.
"""

from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import RoundResultRecorded
from glossogen.models.event_base import EventBase
from glossogen.scenario_authoring.scenario_conformance import check_scenario, failures
from glossogen.scenario_authoring.scenario_scaffold import write_scenario_folder
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.scenario_sources import load_configured_scenario_catalog
from glossogen.testing import (
    assert_no_agent_crashed,
    assert_round_loop_completed,
    assert_scenario_is_registered,
    fast_round_overrides,
    run_scenario,
)

SCENARIO_NAME = "generated_drill"


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """Each test imports a generated project's modules and loads a catalog from it."""
    _ = isolated_scenario_imports


def generated_scenario_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> type[SimulationScenario]:
    """Write the folder into an empty project, enter it, and load the catalog it scans.

    Loading through the configured source is not incidental. Half the contract is
    about how the platform finds a scenario, so checking a class imported by hand
    would skip exactly what a scenario outside glossogen gets wrong.
    """
    write_scenario_folder(scenario_name=SCENARIO_NAME, target_dir=tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)
    load_configured_scenario_catalog(cli_sources=(), runs_dirs=())
    return get_scenario_class(name=SCENARIO_NAME)


def build(scenario_cls: type[SimulationScenario], overrides: dict[str, Any]) -> SimulationScenario:
    """Build the generated scenario from its own shipped preset."""
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config.update(overrides)
    return scenario_cls.create_from_config(config=dict(scenario_cls.prepare_config(config=config)))


def test_a_generated_scenario_passes_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first thing the next steps tell the author to run.

    A generated package that cannot pass `validate` teaches the contract
    wrong, and does it to everyone who generates one.
    """
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    outcomes = check_scenario(scenario_cls=scenario_cls)

    assert outcomes, "the checker examined nothing"
    assert not failures(outcomes), [
        f"{outcome.check}: {outcome.detail}" for outcome in failures(outcomes)
    ]


def test_the_generated_sources_load_the_generated_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scan of the project directory reaches the generated module."""
    assert_scenario_is_registered(scenario_cls=generated_scenario_class(tmp_path, monkeypatch))


async def test_a_generated_scenario_runs_its_round_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two rounds, scripted, end to end: injections render, the world keeps state,
    every round reaches a verdict and the run ends cleanly."""
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    scenario = build(scenario_cls, fast_round_overrides(round_count=2))

    result = await run_scenario(
        scenario=scenario, round_count=2, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=2)
    assert_no_agent_crashed(result=result)


async def test_the_generated_world_scores_the_round_it_says_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scoring rule works, which is what an author edits first.

    The scripted agents chat without relaying the word, so the round fails, and
    the reason names the word that never landed. A template whose verdict was
    stuck at success would pass every other test here.
    """
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    scenario = build(scenario_cls, fast_round_overrides(round_count=1))

    result = await run_scenario(
        scenario=scenario, round_count=1, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    verdicts = result.of_type(event_type=RoundResultRecorded)
    assert len(verdicts) == 1
    assert verdicts[0].success is False
    assert "never relayed" in verdicts[0].reason


async def test_the_generated_event_reaches_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated event is declared in `event_types()` and parses back out of the JSONL.

    The event logger refuses an undeclared event, and a reader reads one as an
    `UnrecognizedEvent`, so this is where a scaffold that forgot to declare it would show.
    """
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    scenario = build(scenario_cls, fast_round_overrides(round_count=1))

    result = await run_scenario(
        scenario=scenario, round_count=1, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    # The event class exists only in the generated package, so it is reached by name.
    round_opened: type[EventBase] = import_module(
        f"{SCENARIO_NAME}.{SCENARIO_NAME}"
    ).GeneratedDrillRoundOpened
    opened = result.of_type(event_type=round_opened)
    assert len(opened) == 1
    assert getattr(opened[0], "code_word")
