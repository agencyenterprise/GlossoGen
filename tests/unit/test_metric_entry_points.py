"""Which metrics a scenario's runs can be scored by, and where each comes from.

A metric reaches the evaluation runner through ``available_metrics``, which
imports the classes, and reaches the `--metrics` validation and the UI's metric
list through ``available_metric_names``, which reads installed metrics by name
only. Both cover the generic metrics, the scenario's own ``scenario_metrics()``,
and metrics other distributions declare, and the tests here hold them in
agreement.
"""

import logging
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import cast

import pytest

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_entry_points import (
    METRIC_ENTRY_POINT_GROUP,
    external_metric_names,
)
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_registry import (
    GENERIC_METRIC_REGISTRY,
    available_metrics,
)
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.scenario_metric_names import available_metric_names
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.models.message import SimulationMessage
from glossogen.scenario_contract.catalog import current_scenario_catalog
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.scenarios.veyru.scenario import VeyruScenario
from glossogen.testing.scenario_runtime import build_scenario
from tests.unit.test_scenario_loader import declare_in_groups

BUILT_IN_SCENARIOS = dict(current_scenario_catalog().classes())

FAKE_MODULE = "tests.fakes.external_metric"
EXTERNAL_NAME = "external_word_count"


def message_on(channel_id: str, text: str) -> MessageSent:
    """Build one ``message_sent`` event on a channel."""
    return MessageSent(
        round_number=1,
        token_count=0,
        message=SimulationMessage(
            message_id=f"m-{text[:8]}",
            channel_id=channel_id,
            sender_agent_id="somebody",
            sender_display_name="Somebody",
            text=text,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            round_number=1,
        ),
    )


def entry_point(name: str, attribute: str) -> EntryPoint:
    """Build an entry point naming something in the fake external metric module."""
    return EntryPoint(
        name=name,
        value=f"{FAKE_MODULE}:{attribute}",
        group=METRIC_ENTRY_POINT_GROUP,
    )


def declare(monkeypatch: pytest.MonkeyPatch, *points: EntryPoint) -> None:
    """Make the given entry points look installed."""

    declare_in_groups(monkeypatch, {METRIC_ENTRY_POINT_GROUP: list(points)})


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


class ShadowingScenario(SignalGameScenario):
    """signal_game, declaring a metric under a generic metric's name."""

    @classmethod
    def scenario_metrics(cls) -> tuple[type[Metric], ...]:
        """The shadowing metric only."""
        return (ShadowingMetric,)


class DuplicatingScenario(SignalGameScenario):
    """signal_game, declaring its own metric twice."""

    @classmethod
    def scenario_metrics(cls) -> tuple[type[Metric], ...]:
        """excess_moves, twice."""
        own = SignalGameScenario.scenario_metrics()[0]
        return (own, own)


def test_a_scenario_without_metrics_of_its_own_gets_the_generic_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing installed, veyru's registry is exactly the generic metrics."""
    declare(monkeypatch)

    assert available_metrics(scenario_cls=VeyruScenario) == GENERIC_METRIC_REGISTRY


def test_the_two_generic_metric_lists_agree() -> None:
    """`GENERIC_METRIC_NAMES` and the registry are maintained by hand, separately.

    The registry is what can run; the name list is what the API and `--metrics`
    accept, kept apart so a listing does not import every metric class. Adding a
    metric to one and not the other gives either a metric nothing can ask for, or
    a name that is accepted and then fails to resolve.
    """
    assert set(GENERIC_METRIC_NAMES) == set(GENERIC_METRIC_REGISTRY)


def test_a_scenario_metric_is_offered_and_runnable_for_its_own_scenario_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """signal_game's metrics resolve on signal_game's runs and on no other's.

    The runner resolves through the same lookup, so asking for one on a veyru run
    is an unknown metric rather than a run that reports nothing.
    """
    declare(monkeypatch)

    for scenario_metric in SignalGameScenario.scenario_metrics():
        assert scenario_metric.name in available_metric_names(scenario_cls=SignalGameScenario)
        assert available_metrics(scenario_cls=SignalGameScenario)[scenario_metric.name] is (
            scenario_metric
        )
        assert scenario_metric.name not in available_metric_names(scenario_cls=VeyruScenario)
        assert scenario_metric.name not in available_metrics(scenario_cls=VeyruScenario)


def test_a_scenario_metric_cannot_take_a_generic_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generic metric keeps the name, so reports stay comparable across scenarios."""
    declare(monkeypatch)

    registry = available_metrics(scenario_cls=ShadowingScenario)

    assert registry["round_success"] is GENERIC_METRIC_REGISTRY["round_success"]


def test_a_scenario_metric_taking_a_generic_name_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Ignoring it silently would leave the scenario's author looking for a missing number."""
    declare(monkeypatch)

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
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A repeat of the scenario's own name is not reported as a clash with a generic one."""
    declare(monkeypatch)

    with caplog.at_level(logging.ERROR):
        registry = available_metrics(scenario_cls=DuplicatingScenario)

    errors = [record.message for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "more than once" in errors[0]
    assert "excess_moves" in registry


def test_a_run_whose_scenario_is_gone_still_has_the_generic_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading an old run must not depend on its scenario still being installed."""
    declare(monkeypatch)

    assert available_metrics(scenario_cls=None) == GENERIC_METRIC_REGISTRY


def test_a_run_whose_scenario_is_gone_still_has_installed_metrics_and_no_scenarios(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no scenario to ask, nobody's scenario metrics are offered."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    registry = available_metrics(scenario_cls=None)

    assert set(registry) == set(GENERIC_METRIC_REGISTRY) | {EXTERNAL_NAME}
    for scenario_metric in SignalGameScenario.scenario_metrics():
        assert scenario_metric.name not in registry


def test_an_external_metric_becomes_runnable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registry the evaluation runner reads includes it."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    registry = available_metrics(scenario_cls=VeyruScenario)

    assert EXTERNAL_NAME in registry
    assert registry[EXTERNAL_NAME].name == EXTERNAL_NAME
    assert set(GENERIC_METRIC_REGISTRY) <= set(registry), "a built-in metric went missing"


def test_an_external_metric_is_advertised_by_every_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--metrics` is validated against this list, so it has to include it."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    for scenario_cls in BUILT_IN_SCENARIOS.values():
        assert EXTERNAL_NAME in available_metric_names(scenario_cls=scenario_cls)


def test_advertised_and_runnable_stay_in_agreement(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two lists are built by different routes, so they can drift apart.

    One is read from metadata without importing, the other by importing the
    classes. A metric advertised but not runnable is rejected at launch; one
    runnable but not advertised cannot be asked for through the API at all.
    """
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    for scenario_cls in BUILT_IN_SCENARIOS.values():
        advertised = set(available_metric_names(scenario_cls=scenario_cls))
        runnable = set(available_metrics(scenario_cls=scenario_cls))
        assert advertised == runnable, scenario_cls.name()


def test_advertised_and_runnable_agree_with_nothing_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same agreement when only generic and scenario metrics are in play."""
    declare(monkeypatch)

    for scenario_cls in BUILT_IN_SCENARIOS.values():
        advertised = set(available_metric_names(scenario_cls=scenario_cls))
        runnable = set(available_metrics(scenario_cls=scenario_cls))
        assert advertised == runnable, scenario_cls.name()


def test_a_built_in_metric_name_cannot_be_taken_over(monkeypatch: pytest.MonkeyPatch) -> None:
    """A report is keyed by metric name, so redefining one breaks comparability."""
    declare(monkeypatch, entry_point(name="round_success", attribute="ExternalWordCountMetric"))

    assert (
        available_metrics(scenario_cls=VeyruScenario)["round_success"]
        is GENERIC_METRIC_REGISTRY["round_success"]
    )


def test_a_metric_whose_class_name_disagrees_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measurement would land under a name nobody asked for."""
    declare(monkeypatch, entry_point(name="declared_as_this", attribute="MisnamedMetric"))

    assert "declared_as_this" not in available_metrics(scenario_cls=VeyruScenario)


def test_an_entry_point_naming_the_wrong_object_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pointing at a non-Metric drops that metric, not the whole evaluation."""
    declare(monkeypatch, entry_point(name="not_a_metric", attribute="NOT_A_METRIC"))

    registry = available_metrics(scenario_cls=VeyruScenario)

    assert "not_a_metric" not in registry
    assert set(GENERIC_METRIC_REGISTRY) <= set(registry), "one bad metric took the others down"


def test_a_metric_that_fails_to_import_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same tolerance for a module that raises on import."""
    declare(
        monkeypatch,
        EntryPoint(
            name="explodes",
            value="tests.fakes.no_such_module:Whatever",
            group=METRIC_ENTRY_POINT_GROUP,
        ),
    )

    registry = available_metrics(scenario_cls=VeyruScenario)

    assert "explodes" not in registry
    assert set(GENERIC_METRIC_REGISTRY) <= set(registry)


async def test_an_external_metric_actually_scores_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolving it is not the same as it working.

    Runs the metric the way the evaluation runner does, over a hand-built event
    log, and checks the Measurement it produces. Nothing about registration
    proves a metric can read an event log and report a number.
    """
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))
    metric = available_metrics(scenario_cls=VeyruScenario)[EXTERNAL_NAME]()
    scenario = build_scenario(scenario_name="veyru", preset_name="knobs_default", overrides={})
    channel_id = scenario.get_primary_channels()[0].channel_id

    events: list[SimulationEvent] = [
        message_on(channel_id=channel_id, text="three words here"),
        message_on(channel_id=channel_id, text="one"),
        message_on(channel_id="somewhere_else", text="not counted at all here"),
    ]
    measurements = await metric.compute(
        events=events,
        agent_configs=[],
        scenario=scenario,
        llm_provider=cast(LLMProvider, None),
        run_dir=Path("."),
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )

    assert len(measurements) == 1
    assert measurements[0].metric_name == EXTERNAL_NAME
    assert measurements[0].score == pytest.approx(2.0), "3 words then 1 word, off-channel ignored"


async def test_an_external_metric_reports_nothing_when_it_does_not_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The empty-list convention, exercised through the registry."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))
    metric = available_metrics(scenario_cls=VeyruScenario)[EXTERNAL_NAME]()
    scenario = build_scenario(scenario_name="veyru", preset_name="knobs_default", overrides={})

    measurements = await metric.compute(
        events=[],
        agent_configs=[],
        scenario=scenario,
        llm_provider=cast(LLMProvider, None),
        run_dir=Path("."),
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )

    assert measurements == []


def test_names_are_read_without_importing_the_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property that keeps the scenario contract out of the import cycle.

    A name that cannot be imported at all still lists, because listing reads
    installed metadata rather than loading anything.
    """
    declare(
        monkeypatch,
        EntryPoint(
            name="unimportable",
            value="tests.fakes.no_such_module:Whatever",
            group=METRIC_ENTRY_POINT_GROUP,
        ),
    )

    assert external_metric_names() == ["unimportable"]
