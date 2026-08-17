"""The conformance checks covering a scenario's events and its metric hooks.

Every check here guards a failure that is silent at the time it happens. A repeated
`event_type` shadows one side of the parser, so the run writes fine and reads back
afterwards as something else. An `events` module that raises is logged and skipped
by discovery, on purpose, so a third-party plug-in cannot stop the platform reading
unrelated logs, which also means its author is never told. A probe config naming a
file that is not there makes every metric in that family report having nothing to
measure, which is what a run with nothing to measure reports too.

Each test breaks one thing against a real scenario and asserts the check says so,
through `check_scenario`, which is what the CLI calls. Passing on an intact scenario
is covered by the conformance suite, which runs all of this over every built-in and
every preset.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import Field

from glossogen.models.event_base import EventBase
from glossogen.models.model_consumer import ModelConsumer
from glossogen.scenario_conformance import CheckOutcome, check_scenario
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.prisoners_dilemma import events as pd_events

SCENARIO = "prisoners_dilemma"

COLLISION = "events do not collide with the platform's"
LITERAL = "events declare a literal event_type"
PARSER = "events parse alongside the platform's"
BASE_IMPORT = "events.py imports only the event base"
JUDGES = "declared judge models are readable"
PROBE = "the probe config points at files that exist"


def outcomes_for(check_name: str, scenario_name: str) -> list[CheckOutcome]:
    """Return what one named check said, across every preset the scenario ships."""
    found = [
        outcome
        for outcome in check_scenario(scenario_cls=get_scenario_class(name=scenario_name))
        if outcome.check == check_name
    ]
    assert found, f"no check named {check_name!r} ran against {scenario_name}"
    return found


def failed(check_name: str, scenario_name: str) -> CheckOutcome:
    """Assert the named check failed, and return the first failure it reported."""
    broken = [outcome for outcome in outcomes_for(check_name, scenario_name) if not outcome.passed]
    assert broken, f"{check_name!r} passed against a scenario it should have rejected"
    return broken[0]


def passes(check_name: str, scenario_name: str) -> bool:
    """Whether the named check passed against every preset."""
    return all(outcome.passed for outcome in outcomes_for(check_name, scenario_name))


def scenario_package_dir() -> Path:
    """The directory `prisoners_dilemma` ships from."""
    scenario_cls = get_scenario_class(name=SCENARIO)
    prepared = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    )
    scenario = scenario_cls.create_from_config(config=dict(prepared))
    return Path(str(scenario.scenario_package_files()))


@pytest.fixture(name="declare_event")
def declare_event_fixture() -> Any:
    """Add an event class to the scenario's events module, and remove it after.

    Declared in the module rather than by patching a discovery result, because the
    module is what the check reads: `EventBase.__subclasses__` holds every
    scenario's events at once and cannot say whose is whose.
    """
    added: list[type[EventBase]] = []

    def declare(event_cls: type[EventBase]) -> None:
        event_cls.__module__ = pd_events.__name__
        setattr(pd_events, event_cls.__name__, event_cls)
        added.append(event_cls)

    yield declare

    for event_cls in added:
        delattr(pd_events, event_cls.__name__)


def test_an_event_stealing_a_platform_discriminator_is_reported(
    declare_event: Callable[[type[EventBase]], None],
) -> None:
    """Whichever side loses, the run reads back afterwards as the other thing."""

    class Colliding(EventBase):
        """Answers to a name the platform's MessageSent already answers to."""

        event_type: Literal["message_sent"] = "message_sent"

    declare_event(Colliding)
    outcome = failed(COLLISION, SCENARIO)

    assert "message_sent" in outcome.detail
    assert "MessageSent" in outcome.detail


def test_two_of_a_scenarios_own_events_sharing_a_discriminator_are_reported(
    declare_event: Callable[[type[EventBase]], None],
) -> None:
    """The same failure within one scenario, which the platform list cannot catch."""

    class Duplicate(EventBase):
        """Repeats a discriminator prisoners_dilemma already ships."""

        event_type: Literal["pd_decision_submitted"] = "pd_decision_submitted"

    declare_event(Duplicate)

    assert "pd_decision_submitted" in failed(COLLISION, SCENARIO).detail


def test_the_parser_refuses_a_colliding_union_too(
    declare_event: Callable[[type[EventBase]], None],
) -> None:
    """A backstop under the check above, and the reason the union is built at all.

    The collision check runs first and explains it in the scenario's terms; this one
    catches whatever that misses, by building the parser the run's log is read with.
    """

    class Colliding(EventBase):
        """Answers to a platform name."""

        event_type: Literal["round_ended"] = "round_ended"

    declare_event(Colliding)

    assert not passes(PARSER, SCENARIO)


def test_an_event_without_a_fixed_discriminator_is_reported(
    declare_event: Callable[[type[EventBase]], None],
) -> None:
    """`event_type` is what the parser dispatches on, so it cannot vary."""

    class Unfixed(EventBase):
        """Carries no literal, so nothing can dispatch on it."""

        event_type: str = Field(default_factory=str)

    declare_event(Unfixed)

    assert "Unfixed" in failed(LITERAL, SCENARIO).detail


def test_an_events_module_importing_the_event_union_is_reported() -> None:
    """The documented deadlock, checked from the source rather than by importing.

    `models.event` builds its union by importing every scenario's `events` while it
    is itself mid-import, so an `events` module importing back from it closes the
    cycle. By the time that import would fail the platform has failed to start,
    which is why this reads the file instead of importing it.
    """
    events_file = scenario_package_dir() / "events.py"
    original = events_file.read_text(encoding="utf-8")
    try:
        events_file.write_text(
            "from glossogen.models.event import MessageSent\n" + original, encoding="utf-8"
        )
        detail = failed(BASE_IMPORT, SCENARIO).detail
    finally:
        events_file.write_text(original, encoding="utf-8")

    assert "event_base" in detail


def test_a_judge_with_a_blank_model_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the hook reports is believed, so a launch has to be able to read it."""

    def blank_judge(
        cls: type[SimulationScenario], knobs: dict[str, Any] | None
    ) -> tuple[ModelConsumer, ...]:
        """Report a judge whose model is whitespace."""
        _ = cls, knobs
        return (ModelConsumer(name="round judge", model="  ", provider="anthropic"),)

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "get_judge_models", classmethod(blank_judge)
    )

    assert "round judge" in failed(JUDGES, SCENARIO).detail


def test_a_judge_declaration_is_not_compared_against_the_knobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scenario reporting no judge is believed, whatever its knobs say.

    This comparison was written and then removed on the branch that added the launch
    check: a scenario scoring its rounds without an LLM declared the knobs anyway,
    and comparing the two refused runs for a credential it would never spend. What
    the hook reports is the scenario's to decide.
    """

    def no_judge(
        cls: type[SimulationScenario], knobs: dict[str, Any] | None
    ) -> tuple[ModelConsumer, ...]:
        """Report that this scenario calls no model of its own."""
        _ = cls, knobs
        return ()

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "get_judge_models", classmethod(no_judge)
    )

    assert passes(JUDGES, SCENARIO)


def test_a_probe_config_naming_a_missing_bank_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise every metric in the probe family reports nothing to measure."""
    scenario_cls = get_scenario_class(name="veyru")
    prepared = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    )
    config = scenario_cls.create_from_config(config=dict(prepared)).get_protocol_probe_config()
    assert config is not None, "veyru is the scenario that implements this hook"

    def missing_bank(self: object) -> object:
        """Point the config at a question bank that is not on disk."""
        _ = self
        return config._replace(questions_path=config.questions_path.parent / "gone.json")

    monkeypatch.setattr(scenario_cls, "get_protocol_probe_config", missing_bank)

    assert "gone.json" in failed(PROBE, "veyru").detail


def test_a_scenario_without_a_probe_config_passes() -> None:
    """The hook opts out by returning None, and opting out is not a failure."""
    assert passes(PROBE, SCENARIO)
