"""Which metrics a scenario's runs can be scored by.

A metric reaches the evaluation runner through ``available_metrics``, which
imports the classes, and reaches the `--metrics` validation and the UI's metric
list through ``available_metric_names``. Both cover the generic metrics and the
scenario's own ``scenario_metrics()``, and the tests here hold them in agreement.
"""

import logging
from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_registry import (
    GENERIC_METRIC_REGISTRY,
    available_metrics,
)
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.scenario_metric_names import available_metric_names
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.registration import scenario
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario


class ShadowingMetric(Metric):
    """A scenario metric that reuses a generic metric's name."""

    name = "round_success"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Never run; only its name is under test."""
        _ = events, agent_configs, scenario, llm_provider, run_dir, options
        return []


@scenario(name="shadowing_signal_game")
class ShadowingScenario(SignalGameScenario):
    """signal_game, declaring a metric under a generic metric's name."""

    @classmethod
    def scenario_metrics(cls) -> tuple[type[Metric], ...]:
        """The shadowing metric only."""
        return (ShadowingMetric,)


@scenario(name="duplicating_signal_game")
class DuplicatingScenario(SignalGameScenario):
    """signal_game, declaring its own metric twice."""

    @classmethod
    def scenario_metrics(cls) -> tuple[type[Metric], ...]:
        """excess_moves, twice."""
        own = SignalGameScenario.scenario_metrics()[0]
        return (own, own)


def test_a_scenario_without_metrics_of_its_own_gets_the_generic_ones() -> None:
    """veyru's registry is exactly the generic metrics."""
    assert available_metrics(scenario_cls=VeyruScenario) == GENERIC_METRIC_REGISTRY


def test_the_two_generic_metric_lists_agree() -> None:
    """`GENERIC_METRIC_NAMES` and the registry are maintained by hand, separately.

    The registry is what can run; the name list is what the API and `--metrics`
    accept, kept apart so a listing does not import every metric class. Adding a
    metric to one and not the other gives either a metric nothing can ask for, or
    a name that is accepted and then fails to resolve.
    """
    assert set(GENERIC_METRIC_NAMES) == set(GENERIC_METRIC_REGISTRY)


def test_a_scenario_metric_is_offered_and_runnable_for_its_own_scenario_only() -> None:
    """signal_game's metrics resolve on signal_game's runs and on no other's.

    The runner resolves through the same lookup, so asking for one on a veyru run
    is an unknown metric rather than a run that reports nothing.
    """
    for scenario_metric in SignalGameScenario.scenario_metrics():
        assert scenario_metric.name in available_metric_names(scenario_cls=SignalGameScenario)
        assert available_metrics(scenario_cls=SignalGameScenario)[scenario_metric.name] is (
            scenario_metric
        )
        assert scenario_metric.name not in available_metric_names(scenario_cls=VeyruScenario)
        assert scenario_metric.name not in available_metrics(scenario_cls=VeyruScenario)


def test_a_scenario_metric_cannot_take_a_generic_name() -> None:
    """The generic metric keeps the name, so reports stay comparable across scenarios."""
    registry = available_metrics(scenario_cls=ShadowingScenario)

    assert registry["round_success"] is GENERIC_METRIC_REGISTRY["round_success"]


def test_a_scenario_metric_taking_a_generic_name_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ignoring it silently would leave the scenario's author looking for a missing number."""
    with caplog.at_level(logging.ERROR):
        available_metrics(scenario_cls=ShadowingScenario)

    shadowing = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR and "repeats a generic metric's name" in record.message
    ]
    assert len(shadowing) == 1
    assert repr(ShadowingScenario.name()) in shadowing[0].message
    assert "round_success" in shadowing[0].message


def test_a_scenario_metric_declared_twice_is_logged_as_a_duplicate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A repeat of the scenario's own name is not reported as a clash with a generic one."""
    with caplog.at_level(logging.ERROR):
        registry = available_metrics(scenario_cls=DuplicatingScenario)

    errors = [record.message for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "more than once" in errors[0]
    assert "excess_moves" in registry


def test_a_run_whose_scenario_is_gone_still_has_the_generic_metrics() -> None:
    """Reading an old run must not depend on its scenario being loaded."""
    assert available_metrics(scenario_cls=None) == GENERIC_METRIC_REGISTRY
