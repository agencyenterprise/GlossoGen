"""How each agent's thinking level is picked, and recovered from logs that predate it.

Before ``agent_thinking`` existed, every OpenAI reasoning model was sent
``openai_reasoning_effort="high"`` and its registration recorded nothing. A resume
or fork of such a run keeps those agents at ``high``, so the rounds after the
boundary run at the effort the rounds before it did.
"""

from typing import Any

import pytest

from glossogen.agent_thinking import (
    AgentThinkingPolicy,
    recorded_thinking_level,
    registration_predates_thinking,
    thinking_policy_for_run,
)
from glossogen.evaluation.log_reader import extract_agent_configs
from glossogen.evaluation.metric_core.mid_run_swap_overrides import apply_mid_run_swaps
from glossogen.model_catalog import Provider
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun, SimulationEvent

OPENAI_REASONING_MODEL = "gpt-5.4"
OPENAI_PLAIN_MODEL = "gpt-4.1-mini"


def registration_line(model: str, provider: str) -> dict[str, Any]:
    """An ``agent_registered`` line as a log recorded before ``thinking`` holds it."""
    return {
        "event_type": "agent_registered",
        "agent_id": "observer",
        "role_name": "Observer",
        "system_prompt": "You observe.",
        "channel_ids": ["link"],
        "tool_names": ["send_message"],
        "model": model,
        "provider": provider,
        "max_tokens": 16384,
        "round_number": 0,
    }


def legacy_registration(model: str, provider: str) -> AgentRegistered:
    return AgentRegistered.model_validate(registration_line(model=model, provider=provider))


def current_registration(model: str, provider: str, thinking: object) -> AgentRegistered:
    line = registration_line(model=model, provider=provider)
    line["thinking"] = thinking
    return AgentRegistered.model_validate(line)


def test_a_registration_logged_now_records_thinking_even_when_unset() -> None:
    """The key's absence is what marks a legacy line, so ``null`` has to be written."""
    written = current_registration(
        model=OPENAI_REASONING_MODEL, provider="openai", thinking=None
    ).model_dump(mode="json")

    assert written["thinking"] is None
    assert not registration_predates_thinking(registration=AgentRegistered.model_validate(written))


@pytest.mark.parametrize(
    ("model", "provider", "expected"),
    [
        (OPENAI_REASONING_MODEL, "openai", "high"),
        (OPENAI_PLAIN_MODEL, "openai", None),
        ("claude-sonnet-4-6", "anthropic", None),
    ],
)
def test_a_legacy_registration_reports_the_level_its_agent_was_sent(
    model: str, provider: str, expected: str | None
) -> None:
    assert recorded_thinking_level(
        registration=legacy_registration(model=model, provider=provider)
    ) == (expected)


def test_a_current_registration_reports_its_own_level() -> None:
    registration = current_registration(
        model=OPENAI_REASONING_MODEL, provider="openai", thinking=None
    )

    assert recorded_thinking_level(registration=registration) is None


def test_a_fresh_run_sends_the_knob_to_every_agent() -> None:
    policy = thinking_policy_for_run(level="low", resumed_registrations=[])

    assert policy.for_agent(model=OPENAI_REASONING_MODEL, provider=Provider.OPENAI) == "low"
    assert policy.for_agent(model="claude-sonnet-4-6", provider=Provider.ANTHROPIC) == "low"


def test_a_fresh_run_without_the_knob_sends_nothing_to_openai() -> None:
    policy = thinking_policy_for_run(level=None, resumed_registrations=[])

    assert policy.for_agent(model=OPENAI_REASONING_MODEL, provider=Provider.OPENAI) is None


def test_resuming_a_legacy_run_keeps_openai_reasoning_models_at_high() -> None:
    policy = thinking_policy_for_run(
        level=None,
        resumed_registrations=[
            legacy_registration(model="claude-sonnet-4-6", provider="anthropic")
        ],
    )

    assert policy == AgentThinkingPolicy(level=None, pins_legacy_level=True)
    assert policy.for_agent(model=OPENAI_REASONING_MODEL, provider=Provider.OPENAI) == "high"
    assert policy.for_agent(model=OPENAI_PLAIN_MODEL, provider=Provider.OPENAI) is None
    assert policy.for_agent(model="claude-sonnet-4-6", provider=Provider.ANTHROPIC) is None


def test_the_knob_overrides_the_legacy_level() -> None:
    policy = thinking_policy_for_run(
        level="minimal",
        resumed_registrations=[
            legacy_registration(model=OPENAI_REASONING_MODEL, provider="openai")
        ],
    )

    assert policy.for_agent(model=OPENAI_REASONING_MODEL, provider=Provider.OPENAI) == "minimal"


def test_resuming_a_current_run_pins_nothing() -> None:
    policy = thinking_policy_for_run(
        level=None,
        resumed_registrations=[
            current_registration(model=OPENAI_REASONING_MODEL, provider="openai", thinking=None)
        ],
    )

    assert policy.for_agent(model=OPENAI_REASONING_MODEL, provider=Provider.OPENAI) is None


def test_configs_rebuilt_for_the_probes_carry_the_recorded_level() -> None:
    """The probes ask each agent under its own model, and now at its own level."""
    events: list[SimulationEvent] = [
        legacy_registration(model=OPENAI_REASONING_MODEL, provider="openai")
    ]

    [config] = extract_agent_configs(events=events)

    assert config.thinking == "high"


def test_a_swapped_in_agent_is_probed_at_its_own_level() -> None:
    registration = current_registration(
        model="claude-sonnet-4-6", provider="anthropic", thinking="xhigh"
    )
    swap = AgentSwappedMidRun(
        agent_id="observer",
        new_model=OPENAI_REASONING_MODEL,
        new_provider="openai",
        channel_visibility={},
        thinking="low",
        round_number=3,
    )
    events: list[SimulationEvent] = [registration, swap]

    [config] = apply_mid_run_swaps(
        agent_configs=extract_agent_configs(events=events), events=events
    )

    assert (config.model, config.thinking) == (OPENAI_REASONING_MODEL, "low")
