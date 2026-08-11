"""Tests for the dot-notation config override parser.

Every knob a run is launched with passes through here: `glossogen run` merges
the `--config` file with trailing `key=value` arguments before any scenario sees
them. A parser that quietly accepts a malformed override launches a run whose
configuration is not the one anybody asked for, and the JSONL records the wrong
one as fact.

The failures are all `SystemExit` because these run at CLI preflight, before a
run directory exists.
"""

from typing import Any

import pytest

from glossogen.config_overrides import (
    apply_overrides,
    normalize_agent_overrides,
    parse_overrides,
    split_agent_overrides,
    validate_agent_override_ids,
)

PROVIDERS = {"anthropic", "openai", "self-hosted"}


def applied(*args: str) -> dict[str, Any]:
    """Parse override arguments and apply them to an empty config."""
    return apply_overrides(config={}, overrides=parse_overrides(raw_args=list(args)))


def test_values_are_parsed_as_json_with_a_string_fallback() -> None:
    """`rounds=5` is an int, `name=alice` is a string, and both are intended."""
    config = applied(
        "rounds=5",
        "duration=1.5",
        "enabled=true",
        "disabled=false",
        "nothing=null",
        "name=alice",
        "easy_round_numbers=[1, 2, 3]",
    )
    assert config == {
        "rounds": 5,
        "duration": 1.5,
        "enabled": True,
        "disabled": False,
        "nothing": None,
        "name": "alice",
        "easy_round_numbers": [1, 2, 3],
    }


def test_a_value_may_contain_equals_signs() -> None:
    """Only the first `=` separates key from value."""
    assert applied("note=a=b=c") == {"note": "a=b=c"}


def test_dotted_keys_build_the_nesting_they_describe() -> None:
    """Intermediate objects are created rather than requiring the caller to."""
    config = applied("agents.observer.model=gpt-5.4", "agents.observer.provider=openai")
    assert config == {"agents": {"observer": {"model": "gpt-5.4", "provider": "openai"}}}


def test_an_override_replaces_a_value_from_the_config_file() -> None:
    """The point of the CLI arguments: they win over the `--config` file."""
    base: dict[str, Any] = {"round_count": 15, "nested": {"kept": 1, "replaced": 2}}
    result = apply_overrides(
        config=base,
        overrides=parse_overrides(raw_args=["round_count=20", "nested.replaced=99"]),
    )
    assert result == {"round_count": 20, "nested": {"kept": 1, "replaced": 99}}


@pytest.mark.parametrize(
    "argument",
    [
        "no_equals_sign",
        "--model=claude-sonnet-4-6",
        "=5",
        "a..b=1",
        "a.=1",
        ".a=1",
    ],
)
def test_malformed_override_arguments_are_rejected(argument: str) -> None:
    """A typo has to stop the launch, not silently configure something else.

    `--model=x` in override position is the one worth naming: it looks like it
    set the model, and without this check it would instead add a config key
    called `--model` that no scenario reads.
    """
    with pytest.raises(SystemExit):
        parse_overrides(raw_args=[argument])


def test_overriding_through_a_scalar_is_rejected() -> None:
    """`a.b=1` where `a` is already a number cannot mean anything sensible."""
    with pytest.raises(SystemExit):
        apply_overrides(config={"a": 5}, overrides=parse_overrides(raw_args=["a.b=1"]))


def test_agents_are_split_out_of_the_scenario_config() -> None:
    """`agents.*` is reserved: it configures models, not the scenario."""
    split = split_agent_overrides(
        config={"round_count": 15, "agents": {"observer": {"model": "gpt-5.4"}}}
    )
    assert split.scenario_config == {"round_count": 15}
    assert split.agent_overrides == {"observer": {"model": "gpt-5.4"}}


def test_a_bare_agent_value_is_read_as_a_model_name() -> None:
    """`agents.observer=gpt-5.4` is the shorthand for setting just the model."""
    split = split_agent_overrides(config={"agents": {"observer": "gpt-5.4"}})
    assert split.agent_overrides == {"observer": {"model": "gpt-5.4"}}


def test_config_without_agents_yields_no_overrides() -> None:
    """The common case: no per-agent models, and the config passes through."""
    split = split_agent_overrides(config={"round_count": 15})
    assert split.scenario_config == {"round_count": 15}
    assert split.agent_overrides == {}


def test_a_non_object_agents_key_is_rejected() -> None:
    """`agents=gpt-5.4` names no agent, so there is nothing to apply it to."""
    with pytest.raises(SystemExit):
        split_agent_overrides(config={"agents": "gpt-5.4"})


def test_provider_defaults_to_the_run_provider() -> None:
    """Overriding only the model keeps the agent on the run's provider."""
    normalized = normalize_agent_overrides(
        agent_overrides={"observer": {"model": "claude-opus-4-6"}},
        default_provider="anthropic",
        valid_providers=PROVIDERS,
    )
    assert normalized == {"observer": {"model": "claude-opus-4-6", "provider": "anthropic"}}


def test_surrounding_whitespace_is_stripped() -> None:
    """A model name with a stray space would not match the pricing table."""
    normalized = normalize_agent_overrides(
        agent_overrides={"observer": {"model": " gpt-5.4 ", "provider": " openai "}},
        default_provider="anthropic",
        valid_providers=PROVIDERS,
    )
    assert normalized == {"observer": {"model": "gpt-5.4", "provider": "openai"}}


@pytest.mark.parametrize(
    "override",
    [
        {"provider": "openai"},
        {"model": "  "},
        {"model": "gpt-5.4", "provider": "  "},
        {"model": "gpt-5.4", "provider": "openai-typo"},
        {"model": "gpt-5.4", "providr": "openai"},
    ],
)
def test_unusable_agent_overrides_are_rejected(override: dict[str, Any]) -> None:
    """An unknown provider or a misspelled key fails now, not mid-run.

    `providr` matters because `extra="forbid"` is what turns a typo into an
    error instead of an override that is accepted and then ignored.
    """
    with pytest.raises(SystemExit):
        normalize_agent_overrides(
            agent_overrides={"observer": override},
            default_provider="anthropic",
            valid_providers=PROVIDERS,
        )


def test_overrides_must_name_agents_the_scenario_has() -> None:
    """A misspelled agent id would otherwise run every agent on the default."""
    with pytest.raises(SystemExit):
        validate_agent_override_ids(
            agent_overrides={"feild_observer": {"model": "gpt-5.4", "provider": "openai"}},
            valid_agent_ids={"field_observer", "stabilization_engineer"},
        )


def test_known_agent_ids_pass() -> None:
    """The success path: every override names a real agent."""
    validate_agent_override_ids(
        agent_overrides={"field_observer": {"model": "gpt-5.4", "provider": "openai"}},
        valid_agent_ids={"field_observer", "stabilization_engineer"},
    )
