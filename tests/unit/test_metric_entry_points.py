"""What it takes for a metric shipped outside glossogen to be usable.

A metric reaches the evaluation runner through the registry, and reaches the
`--metrics` validation and the UI's metric list through
``SimulationScenario.get_available_metric_names``. Both have to know about an
externally-contributed metric, and they cannot know it the same way: a metric
module imports the scenario contract, so the contract can only be told names,
never handed classes. The last test here pins that split.
"""

from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import cast

import pytest

from glossogen.evaluation.metric_core.generic_metric_names import GENERIC_METRIC_NAMES
from glossogen.evaluation.metric_core.metric_entry_points import (
    METRIC_ENTRY_POINT_GROUP,
    external_metric_names,
)
from glossogen.evaluation.metric_core.metric_registry import (
    GENERIC_METRIC_REGISTRY,
    available_metrics,
)
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.models.message import SimulationMessage
from glossogen.scenario_registry import SCENARIO_REGISTRY
from tests.scenarios.scenario_runtime import build_scenario
from tests.unit.test_scenario_loader import declare_in_groups

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


def test_the_built_in_metrics_are_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing declared, the registry is exactly what ships here."""
    declare(monkeypatch)

    assert available_metrics() == GENERIC_METRIC_REGISTRY


def test_the_two_built_in_metric_lists_agree() -> None:
    """`GENERIC_METRIC_NAMES` and the registry are maintained by hand, separately.

    The registry is what can run; the name list is what the API and `--metrics`
    accept. They cannot be one list, because the scenario contract reads the
    names and a metric module imports the scenario contract. Adding a metric to
    one and not the other gives either a metric nothing can ask for, or a name
    that is accepted and then fails to resolve.
    """
    assert set(GENERIC_METRIC_NAMES) == set(GENERIC_METRIC_REGISTRY)


def test_an_external_metric_becomes_runnable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registry the evaluation runner reads includes it."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    registry = available_metrics()

    assert EXTERNAL_NAME in registry
    assert registry[EXTERNAL_NAME].name == EXTERNAL_NAME
    assert set(GENERIC_METRIC_REGISTRY) <= set(registry), "a built-in metric went missing"


def test_an_external_metric_is_advertised_by_every_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--metrics` is validated against this list, so it has to include it."""
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    advertised = SCENARIO_REGISTRY["veyru"].get_available_metric_names()

    assert EXTERNAL_NAME in advertised


def test_advertised_and_runnable_stay_in_agreement(monkeypatch: pytest.MonkeyPatch) -> None:
    """The two lists are built by different routes, so they can drift apart.

    One is read from metadata without importing, the other by importing the
    classes. A metric advertised but not runnable is rejected at launch; one
    runnable but not advertised cannot be asked for through the API at all.
    """
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))

    advertised = set(SCENARIO_REGISTRY["veyru"].get_available_metric_names())
    runnable = set(available_metrics())

    assert advertised == runnable


def test_a_built_in_metric_name_cannot_be_taken_over(monkeypatch: pytest.MonkeyPatch) -> None:
    """A report is keyed by metric name, so redefining one breaks comparability."""
    declare(monkeypatch, entry_point(name="round_success", attribute="ExternalWordCountMetric"))

    assert available_metrics()["round_success"] is GENERIC_METRIC_REGISTRY["round_success"]


def test_a_metric_whose_class_name_disagrees_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measurement would land under a name nobody asked for."""
    declare(monkeypatch, entry_point(name="declared_as_this", attribute="MisnamedMetric"))

    assert "declared_as_this" not in available_metrics()


def test_an_entry_point_naming_the_wrong_object_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pointing at a non-Metric drops that metric, not the whole evaluation."""
    declare(monkeypatch, entry_point(name="not_a_metric", attribute="NOT_A_METRIC"))

    registry = available_metrics()

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

    registry = available_metrics()

    assert "explodes" not in registry
    assert set(GENERIC_METRIC_REGISTRY) <= set(registry)


async def test_an_external_metric_actually_scores_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolving it is not the same as it working.

    Runs the metric the way the evaluation runner does, over a hand-built event
    log, and checks the Measurement it produces. Nothing about registration
    proves a metric can read an event log and report a number.
    """
    declare(monkeypatch, entry_point(name=EXTERNAL_NAME, attribute="ExternalWordCountMetric"))
    metric = available_metrics()[EXTERNAL_NAME]()
    scenario = build_scenario(scenario_name="veyru", overrides={})
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
    metric = available_metrics()[EXTERNAL_NAME]()
    scenario = build_scenario(scenario_name="veyru", overrides={})

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
