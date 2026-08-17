"""A generated scenario package runs, not just parses.

`new-scenario` promises a package that works before anything is edited, and a
template that only looks right is worse than none: the author would debug their
own first change against a broken starting point.

So this generates one, imports it from where it was written, and puts it through
the same two gates the generated README tells its author to run. Nothing is
installed, no LLM is called, and no clock is waited on.
"""

import sys
import tomllib
from importlib import import_module
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import pytest

from glossogen import scenario_loader
from glossogen.scenario_conformance import check_scenario, failures
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_scaffold import write_scenario_package
from glossogen.testing import (
    assert_no_agent_crashed,
    assert_round_loop_completed,
    assert_scenario_is_registered,
    fast_round_overrides,
    run_scenario,
)
from tests.fakes.installed_entry_points import declare_in_groups

SCENARIO_NAME = "generated_drill"


def generated_scenario_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> type[SimulationScenario]:
    """Write a package, put it on the path, and register it the way installing does.

    Registration is not incidental. Half the contract is about how the platform
    finds a scenario, so checking a class the loader cannot resolve would skip
    exactly what an out-of-tree scenario gets wrong. The entry point is read out
    of the generated `pyproject.toml` rather than written here, so a template
    that emits a key disagreeing with `name()` fails in this test.
    """
    package = write_scenario_package(
        scenario_name=SCENARIO_NAME, target_dir=tmp_path, glossogen_ref="v0.0.0"
    )
    # `syspath_prepend` is untyped, and the import below only needs the path on
    # `sys.path`; monkeypatch restores the list itself at teardown.
    monkeypatch.setattr(sys, "path", [str(package.package_dir), *sys.path])

    manifest = tomllib.loads((package.package_dir / "pyproject.toml").read_text())
    declared: dict[str, dict[str, str]] = manifest["project"]["entry-points"]
    as_installed = {
        group: [
            EntryPoint(name=name, value=value, group=group) for name, value in points.items()
        ]
        for group, points in declared.items()
    }
    declare_in_groups(monkeypatch, as_installed)
    scenario_loader.forget_reported_problems()

    module = import_module(f"{SCENARIO_NAME}.scenario")
    scenario_cls: type[SimulationScenario] = module.GeneratedDrillScenario
    return scenario_cls


def build(scenario_cls: type[SimulationScenario], overrides: dict[str, Any]) -> SimulationScenario:
    """Build the generated scenario from its own shipped preset."""
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config.update(overrides)
    return scenario_cls.create_from_config(config=dict(scenario_cls.prepare_config(config=config)))


def test_a_generated_scenario_passes_the_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first thing its README tells the author to run.

    A generated package that cannot pass `validate` teaches the contract
    wrong, and does it to everyone who generates one.
    """
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    outcomes = check_scenario(scenario_cls=scenario_cls)

    assert outcomes, "the checker examined nothing"
    assert not failures(outcomes), [
        f"{outcome.check}: {outcome.detail}" for outcome in failures(outcomes)
    ]


def test_the_generated_entry_point_resolves_to_the_generated_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The key in the generated `pyproject.toml` names the class it generated.

    Declared from one value, so they cannot disagree by hand, and this says so if
    the templates ever drift apart.
    """
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

    verdicts = result.of_type(event_type="round_result_recorded")
    assert len(verdicts) == 1
    assert verdicts[0]["success"] is False
    assert "never relayed" in verdicts[0]["reason"]


async def test_the_generated_event_reaches_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`events.py` is discovered and its event parses back out of the JSONL.

    This is what the "import only event_base" rule protects, and an author who
    breaks it sees their event type vanish rather than raise.
    """
    scenario_cls = generated_scenario_class(tmp_path, monkeypatch)
    scenario = build(scenario_cls, fast_round_overrides(round_count=1))

    result = await run_scenario(
        scenario=scenario, round_count=1, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    opened = result.of_type(event_type=f"{SCENARIO_NAME}_round_opened")
    assert len(opened) == 1
    assert opened[0]["code_word"]
