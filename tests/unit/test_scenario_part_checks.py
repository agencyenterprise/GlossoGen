"""The conformance checks covering what a scenario declares as its own parts.

A scenario hands the platform its own metrics through ``scenario_metrics()`` and its
run-detail extension through ``run_detail_extension()``. Both fail quietly when
wrong. A scenario metric reusing a generic name is ignored by the registry, so the
scenario's number never reaches a report. An extension whose extras model names
another scenario is validated as that one's payload by the discriminated union.

Each test breaks one declaration on a real scenario through ``monkeypatch`` and
asserts the check reports it, through ``check_scenario``, which is what the CLI
calls. Passing on the intact scenarios is asserted here for the scenarios that
declare these parts; the conformance suite covers every built-in as well.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Literal

import pytest
from pydantic import BaseModel

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario
from glossogen.scenario_base import ScenarioBase
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_run_detail_extension import (
    ScenarioRunDetailExtension,
    ScenarioRunExtrasBase,
)
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario

METRICS = "scenario metrics are well formed"
EXTENSION = "the run-detail extension names the scenario"


def outcomes_for(check_name: str, scenario_cls: type[SimulationScenario]) -> list[CheckOutcome]:
    """Return what one named check said, across every preset the scenario ships."""
    found = [
        outcome
        for outcome in check_scenario(scenario_cls=scenario_cls)
        if outcome.check == check_name
    ]
    assert found, f"no check named {check_name!r} ran against {scenario_cls.name()}"
    return found


def failure_detail(check_name: str, scenario_cls: type[SimulationScenario]) -> str:
    """Assert the named check failed, and return what the first failure said."""
    broken = [o for o in outcomes_for(check_name, scenario_cls) if not o.passed]
    assert broken, f"{check_name!r} passed against a scenario it should have rejected"
    return broken[0].detail


def passes(check_name: str, scenario_cls: type[SimulationScenario]) -> bool:
    """Whether the named check passed against every preset."""
    return all(outcome.passed for outcome in outcomes_for(check_name, scenario_cls))


def declare_metrics(
    monkeypatch: pytest.MonkeyPatch,
    scenario_cls: type[SimulationScenario],
    metrics: tuple[type[Metric], ...],
) -> None:
    """Make ``scenario_cls.scenario_metrics()`` return ``metrics``."""

    def declared(cls: type[SimulationScenario]) -> Sequence[type[Metric]]:
        """The metrics under test."""
        _ = cls
        return metrics

    monkeypatch.setattr(scenario_cls, "scenario_metrics", classmethod(declared))


def declare_extension(
    monkeypatch: pytest.MonkeyPatch,
    scenario_cls: type[SimulationScenario],
    extension: ScenarioRunDetailExtension,
) -> None:
    """Make ``scenario_cls.run_detail_extension()`` return ``extension``."""

    def declared(cls: type[SimulationScenario]) -> ScenarioRunDetailExtension:
        """The extension under test."""
        _ = cls
        return extension

    monkeypatch.setattr(scenario_cls, "run_detail_extension", classmethod(declared))


class NamedMetric(Metric):
    """A concrete metric with a name no generic metric uses."""

    name = "scenario_part_check_metric"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Never run; only its declaration is under test."""
        _ = events, agent_configs, scenario, llm_provider, run_dir, options
        return []


class SameNameMetric(NamedMetric):
    """A second class answering to ``NamedMetric``'s name."""


class GenericNameMetric(NamedMetric):
    """A scenario metric reusing a generic metric's name."""

    name = "round_success"


class UnnamedMetric(NamedMetric):
    """A scenario metric whose name is empty."""

    name = ""


class AbstractMetric(Metric):
    """A metric that never implemented ``compute``."""

    name = "scenario_part_check_abstract"


def test_signal_game_metrics_pass() -> None:
    """The scenario shipping metrics of its own declares them correctly."""
    assert SignalGameScenario.scenario_metrics(), "signal_game no longer declares any metric"
    assert passes(METRICS, SignalGameScenario)


def test_a_scenario_metric_with_a_generic_name_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_metrics(monkeypatch, SignalGameScenario, (GenericNameMetric,))

    detail = failure_detail(METRICS, SignalGameScenario)

    assert "round_success" in detail
    assert "GenericNameMetric" in detail


def test_two_scenario_metrics_sharing_a_name_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_metrics(monkeypatch, SignalGameScenario, (NamedMetric, SameNameMetric))

    assert NamedMetric.name in failure_detail(METRICS, SignalGameScenario)


def test_a_scenario_metric_without_a_name_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    declare_metrics(monkeypatch, SignalGameScenario, (UnnamedMetric,))

    assert "has no name" in failure_detail(METRICS, SignalGameScenario)


def test_an_abstract_scenario_metric_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registry would fail only when someone asked for the metric."""
    declare_metrics(monkeypatch, SignalGameScenario, (AbstractMetric,))

    assert "abstract" in failure_detail(METRICS, SignalGameScenario)


class OtherScenarioExtras(ScenarioRunExtrasBase):
    """An extras payload claiming to be signal_game's."""

    scenario_name: Literal["signal_game"] = "signal_game"


class NoDefaultExtras(ScenarioRunExtrasBase):
    """veyru's discriminator declared as a literal with no default."""

    scenario_name: Literal["veyru"]


class PlainStringExtras(ScenarioRunExtrasBase):
    """A ``scenario_name`` typed as any string, which cannot discriminate."""

    scenario_name: str = "veyru"


class NoDiscriminatorExtras(ScenarioRunExtrasBase):
    """An extras payload with no ``scenario_name`` at all."""

    message_count: int


def extension_for(extras_cls: type[ScenarioRunExtrasBase]) -> ScenarioRunDetailExtension:
    """Build an extension whose payload is ``extras_cls``."""

    class Extension(ScenarioRunDetailExtension):
        """Never asked to build; only its payload model is checked."""

        extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]] = extras_cls
        sse_event_classes: ClassVar[tuple[type[BaseModel], ...]] = ()

        def build_extras(
            self,
            events: list[SimulationEvent],
            agents_by_id: dict[str, AgentDetail],
            messages: list[ChannelMessage],
        ) -> ScenarioRunExtrasBase:
            """Not called by the check."""
            _ = events, agents_by_id, messages
            raise AssertionError("the check must not build extras")

    return Extension()


@pytest.mark.parametrize(
    "scenario_name",
    [
        "veyru",
        "drive_module_repair",
        "orbital_anomaly",
        "spot_the_difference",
        "container_yard_stacking",
    ],
)
def test_the_shipped_extensions_name_their_scenario(scenario_name: str) -> None:
    scenario_cls = get_scenario_class(name=scenario_name)
    assert scenario_cls.run_detail_extension() is not None, f"{scenario_name} lost its extension"

    assert passes(EXTENSION, scenario_cls)


def test_a_scenario_without_an_extension_passes() -> None:
    assert SignalGameScenario.run_detail_extension() is None
    assert passes(EXTENSION, SignalGameScenario)


def test_an_extension_naming_another_scenario_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_extension(monkeypatch, VeyruScenario, extension_for(OtherScenarioExtras))

    detail = failure_detail(EXTENSION, VeyruScenario)

    assert "'signal_game'" in detail
    assert "'veyru'" in detail


def test_an_extension_without_a_discriminator_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declare_extension(monkeypatch, VeyruScenario, extension_for(NoDiscriminatorExtras))

    assert "has no scenario_name field" in failure_detail(EXTENSION, VeyruScenario)


def test_an_extension_whose_literal_has_no_default_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The literal is what discriminates; a default is not needed for that."""
    declare_extension(monkeypatch, VeyruScenario, extension_for(NoDefaultExtras))

    assert passes(EXTENSION, VeyruScenario)


def test_an_extension_typing_the_discriminator_as_a_plain_string_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A default naming the scenario is not enough when the type admits any name."""
    declare_extension(monkeypatch, VeyruScenario, extension_for(PlainStringExtras))

    assert "PlainStringExtras" in failure_detail(EXTENSION, VeyruScenario)
