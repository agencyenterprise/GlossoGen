"""The conformance checks covering a scenario's events and its metric hooks.

Every check here guards a failure that is silent at the time it happens. An event
class the scenario defines but leaves out of `event_types()` is refused by the event
logger, and the first sign is a failed run. A probe config naming a file that is not
there makes every metric in that family report having nothing to measure, which is
what a run with nothing to measure reports too. A repeated or unfixed `event_type` is
refused when the catalog loads, so it is tested with the catalog.

Each test breaks one thing against a real scenario and asserts the check says so,
through `check_scenario`, which is what the CLI calls. Passing on an intact scenario
is covered by the conformance suite, which runs all of this over every built-in and
every preset.
"""

import inspect
from collections.abc import Callable
from typing import Any, Literal, Protocol

import pytest

from glossogen.model_catalog.provider_catalog import Provider
from glossogen.models.event_base import EventBase
from glossogen.models.model_consumer import ModelConsumer
from glossogen.models.runner_prompts import RunnerPrompts
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario
from glossogen.scenario_contract.loader import get_scenario_class
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.prisoners_dilemma import events as pd_events

SCENARIO = "prisoners_dilemma"

DECLARED = "defined events are declared"
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
    broken = [
        outcome
        for outcome in outcomes_for(check_name=check_name, scenario_name=scenario_name)
        if not outcome.passed
    ]
    assert broken, f"{check_name!r} passed against a scenario it should have rejected"
    return broken[0]


def passes(check_name: str, scenario_name: str) -> bool:
    """Whether the named check passed against every preset."""
    return all(
        outcome.passed
        for outcome in outcomes_for(check_name=check_name, scenario_name=scenario_name)
    )


class DeclareEvent(Protocol):
    """Adds an event class to what the scenario under test declares."""

    def __call__(self, event_cls: type[EventBase]) -> None: ...


@pytest.fixture(name="declare_event")
def declare_event_fixture(monkeypatch: pytest.MonkeyPatch) -> DeclareEvent:
    """Add an event class to what the scenario returns from `event_types()`.

    The class is also placed in the scenario's events module, as an author would
    write it, so the check for undeclared events sees it as the scenario's own.
    """
    scenario_cls = get_scenario_class(name=SCENARIO)
    declared = list(scenario_cls.event_types())

    def event_types(cls: type[SimulationScenario]) -> tuple[type[EventBase], ...]:
        _ = cls
        return tuple(declared)

    monkeypatch.setattr(scenario_cls, "event_types", classmethod(event_types))

    def declare(event_cls: type[EventBase]) -> None:
        define_in_the_events_module(event_cls=event_cls, monkeypatch=monkeypatch)
        declared.append(event_cls)

    return declare


def define_in_the_events_module(
    event_cls: type[EventBase], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make ``event_cls`` a class of the scenario's events module until the test ends."""
    event_cls.__module__ = pd_events.__name__
    event_cls.__qualname__ = event_cls.__name__
    monkeypatch.setattr(pd_events, event_cls.__name__, event_cls, raising=False)


def test_an_event_the_scenario_defines_but_does_not_declare_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The logger would refuse it at the first emit, minutes into a paid run."""

    class Forgotten(EventBase):
        """Defined beside the scenario's other events and left out of event_types()."""

        event_type: Literal["pd_forgotten"] = "pd_forgotten"

    define_in_the_events_module(event_cls=Forgotten, monkeypatch=monkeypatch)

    assert (
        f"{pd_events.__name__}.Forgotten"
        in failed(check_name=DECLARED, scenario_name=SCENARIO).detail
    )


def test_an_event_declared_by_the_scenario_passes(
    declare_event: DeclareEvent,
) -> None:
    """Declaring the same class is the fix the failure above asks for."""

    class Remembered(EventBase):
        """Defined beside the scenario's other events and declared."""

        event_type: Literal["pd_remembered"] = "pd_remembered"

    declare_event(event_cls=Remembered)

    assert passes(check_name=DECLARED, scenario_name=SCENARIO)


def test_an_event_another_loaded_scenario_declares_is_not_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two scenarios can share a package; each declares its own events, not the other's."""

    class Neighbours(EventBase):
        """Defined in this scenario's package, declared by a different scenario."""

        event_type: Literal["neighbours_event"] = "neighbours_event"

    define_in_the_events_module(event_cls=Neighbours, monkeypatch=monkeypatch)

    def neighbour_event_types(cls: type[SimulationScenario]) -> tuple[type[EventBase], ...]:
        _ = cls
        return (Neighbours,)

    monkeypatch.setattr(
        get_scenario_class(name="veyru"), "event_types", classmethod(neighbour_event_types)
    )

    assert passes(check_name=DECLARED, scenario_name=SCENARIO)


def test_a_judge_with_a_blank_model_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """What the hook reports is believed, so a launch has to be able to read it."""

    def blank_judge(
        cls: type[SimulationScenario], knobs: dict[str, Any] | None
    ) -> tuple[ModelConsumer, ...]:
        """Report a judge whose model is whitespace."""
        _ = cls, knobs
        return (ModelConsumer(name="round judge", model="  ", provider=Provider.ANTHROPIC),)

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "get_judge_models", classmethod(blank_judge)
    )

    assert "round judge" in failed(check_name=JUDGES, scenario_name=SCENARIO).detail


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

    assert passes(check_name=JUDGES, scenario_name=SCENARIO)


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

    assert "gone.json" in failed(check_name=PROBE, scenario_name="veyru").detail


def test_a_scenario_without_a_probe_config_passes() -> None:
    """The hook opts out by returning None, and opting out is not a failure."""
    assert passes(check_name=PROBE, scenario_name=SCENARIO)


SEND_PARAMETERS = "send_message parameters are typed"


async def _untyped_send(agent_id: str, text: str) -> None:
    """A send executor whose signature reports ``text`` with no annotation."""
    _ = agent_id, text


_untyped_send.__signature__ = inspect.Signature(  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]
    parameters=[
        inspect.Parameter("agent_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
        inspect.Parameter("text", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    ]
)


async def _send_without_agent(text: str) -> None:
    """A send executor the platform has no way to tell who is sending."""
    _ = text


def test_the_default_send_executor_passes() -> None:
    assert passes(check_name=SEND_PARAMETERS, scenario_name=SCENARIO)


@pytest.mark.parametrize(
    ("executor", "expected"),
    [(_untyped_send, "without a type annotation: ['text']"), (_send_without_agent, "agent_id")],
)
def test_a_send_executor_the_schema_cannot_describe_is_reported(
    executor: Callable[..., Any], expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def returning_executor(self: SimulationScenario) -> Callable[..., Any]:
        _ = self
        return executor

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "send_message_executor", returning_executor
    )
    assert expected in failed(check_name=SEND_PARAMETERS, scenario_name=SCENARIO).detail


HIDDEN_READ = "hidden base tools are base tools"
RUNNER_PROMPTS = "runner prompts render for every agent"


def test_hiding_read_notifications_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def hiding_read_notifications(self: SimulationScenario, agent_id: str) -> frozenset[str]:
        _ = self, agent_id
        return frozenset({"read_notifications"})

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "hidden_base_tools", hiding_read_notifications
    )
    assert "cannot be hidden" in failed(check_name=HIDDEN_READ, scenario_name=SCENARIO).detail
    monkeypatch.undo()
    assert passes(check_name=HIDDEN_READ, scenario_name=SCENARIO)


def test_hiding_a_tool_that_is_not_a_base_tool_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def hiding_a_scenario_tool(self: SimulationScenario, agent_id: str) -> frozenset[str]:
        _ = self, agent_id
        return frozenset({"stabilize_veyru"})

    monkeypatch.setattr(
        get_scenario_class(name=SCENARIO), "hidden_base_tools", hiding_a_scenario_tool
    )
    assert "stabilize_veyru" in failed(check_name=HIDDEN_READ, scenario_name=SCENARIO).detail


def test_runner_prompts_that_do_not_render_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising_runner_prompts(self: SimulationScenario, agent_id: str) -> RunnerPrompts | None:
        _ = self
        raise KeyError(f"no template for {agent_id}")

    monkeypatch.setattr(get_scenario_class(name=SCENARIO), "runner_prompts", raising_runner_prompts)
    assert "raised KeyError" in failed(check_name=RUNNER_PROMPTS, scenario_name=SCENARIO).detail
    monkeypatch.undo()
    assert passes(check_name=RUNNER_PROMPTS, scenario_name=SCENARIO)
