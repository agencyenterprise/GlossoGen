"""A run is refused at the command line when no agent could reach a model.

The cost of not checking is not a worse error message. Agent runner tasks are
awaited only after the game clock has finished, so a failure on the first call
surfaces after the run's whole configured duration, from a run directory that
was claimed and written and holds a registration for every agent and a call to
no model. The process exits 0. The tests below fix the two halves of avoiding
that: which environments cannot reach a model, and that the refusal happens
before anything is on disk.

Two cases are worth stating twice. A key set to the empty string, because
`.env.example` ships every key blank and a copy that was never filled in reads
as present. And a `self-hosted` model absent from `SELF_HOSTED_BASE_URLS`,
because that map is keyed by exact model strings, so holding the credentials
proves nothing about whether the model is served.
"""

import sys
from pathlib import Path

import pytest

from glossogen import cli
from glossogen.models.agent_config import AgentRole
from glossogen.provider_credentials import (
    ModelConsumer,
    describe_unreachable_providers,
    find_unreachable_providers,
    require_reachable_models,
    resolve_agent_consumers,
)
from glossogen.scenario_loader import get_scenario_class

SENDER = AgentRole(agent_id="sender", role_name="Sender")
RECEIVER = AgentRole(agent_id="receiver", role_name="Receiver")

LLAMA = "meta-llama/Llama-3.3-70B-Instruct"
QWEN = "Qwen/Qwen3-32B"

PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "HF_TOKEN",
    "SELF_HOSTED_BASE_URLS",
    "SELF_HOSTED_API_KEY",
)


def hosted(name: str, model: str) -> ModelConsumer:
    """Return one caller running a self-hosted model."""
    return ModelConsumer(name=name, model=model, provider="self-hosted")


@pytest.fixture(autouse=True)
def empty_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every credential these tests reason about, for every test here.

    The suite-wide fixture hands each test placeholder keys so scenarios can be
    built. That is the opposite of what is under test in this module, so this
    one is autouse to undo it rather than named by each test.
    """
    for name in PROVIDER_KEYS:
        monkeypatch.delenv(name, raising=False)


def test_a_provider_whose_key_is_set_is_not_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="claude", provider="anthropic"),)
    )
    assert unreachable == ()


def test_a_missing_key_names_the_variable_and_the_agents() -> None:
    unreachable = find_unreachable_providers(
        consumers=(
            ModelConsumer(name="sender", model="claude", provider="anthropic"),
            ModelConsumer(name="receiver", model="claude", provider="anthropic"),
        )
    )
    assert len(unreachable) == 1
    assert unreachable[0].provider == "anthropic"
    assert unreachable[0].remedy == "set ANTHROPIC_API_KEY"
    assert unreachable[0].caller_names == ("receiver", "sender")


def test_a_key_set_to_blank_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env.example` ships every key empty, so this is the copied-and-unfilled case."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="claude", provider="anthropic"),)
    )
    assert [entry.remedy for entry in unreachable] == ["set ANTHROPIC_API_KEY"]


def test_either_accepted_name_satisfies_a_provider_that_reads_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Google provider falls back to `GEMINI_API_KEY`, so that alone is enough."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-something")
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="gemini", provider="google-gla"),)
    )
    assert unreachable == ()


def test_a_provider_with_nothing_to_authenticate_is_never_blocked() -> None:
    """A locally served provider needs no key, and one this table has never heard
    of must not be refused on the strength of that."""
    unreachable = find_unreachable_providers(
        consumers=(
            ModelConsumer(name="sender", model="llama3", provider="ollama"),
            ModelConsumer(name="receiver", model="whatever", provider="something-new"),
        )
    )
    assert unreachable == ()


def test_each_provider_the_run_uses_is_reported_separately() -> None:
    unreachable = find_unreachable_providers(
        consumers=(
            ModelConsumer(name="sender", model="claude", provider="anthropic"),
            ModelConsumer(name="receiver", model="gpt", provider="openai"),
        )
    )
    assert [(entry.provider, entry.caller_names) for entry in unreachable] == [
        ("anthropic", ("sender",)),
        ("openai", ("receiver",)),
    ]


def test_self_hosted_wants_both_the_endpoint_map_and_the_key() -> None:
    unreachable = find_unreachable_providers(consumers=(hosted(name="sender", model=LLAMA),))
    assert [entry.remedy for entry in unreachable] == [
        "set SELF_HOSTED_API_KEY",
        "set SELF_HOSTED_BASE_URLS",
    ]


def test_a_self_hosted_model_the_map_does_not_serve_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holding the credentials proves nothing about the model being served.

    The map is keyed by exact model strings, so a run asking for one it does not
    list dies on its first call exactly as an unset key does.
    """
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", f'{{"{QWEN}":"https://example.modal.run/v1"}}')
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    unreachable = find_unreachable_providers(consumers=(hosted(name="sender", model=LLAMA),))
    assert len(unreachable) == 1
    assert LLAMA in unreachable[0].remedy
    assert QWEN in unreachable[0].remedy


def test_a_self_hosted_model_the_map_serves_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", f'{{"{LLAMA}":"https://example.modal.run/v1"}}')
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    unreachable = find_unreachable_providers(consumers=(hosted(name="sender", model=LLAMA),))
    assert unreachable == ()


def test_an_endpoint_map_that_is_not_json_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """`token_pricing` swallows this and reports no self-hosted models, so a run
    configured this way reaches the runner and fails there instead."""
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", "{not valid json")
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    unreachable = find_unreachable_providers(consumers=(hosted(name="sender", model=LLAMA),))
    assert [entry.remedy for entry in unreachable] == [
        "SELF_HOSTED_BASE_URLS is not a JSON object mapping model names to endpoint URLs"
    ]


def test_an_empty_endpoint_map_says_so_rather_than_listing_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", "{}")
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    unreachable = find_unreachable_providers(consumers=(hosted(name="sender", model=LLAMA),))
    assert [entry.remedy for entry in unreachable] == ["SELF_HOSTED_BASE_URLS lists no models"]


def test_agents_on_different_unserved_models_are_reported_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The remedy names a model, so two agents wanting different ones do not merge."""
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", '{"served/model":"https://example.modal.run/v1"}')
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    unreachable = find_unreachable_providers(
        consumers=(
            hosted(name="sender", model=LLAMA),
            hosted(name="receiver", model=QWEN),
        )
    )
    assert len(unreachable) == 2
    assert {entry.caller_names for entry in unreachable} == {("sender",), ("receiver",)}


def test_an_override_decides_which_provider_an_agent_is_checked_against() -> None:
    """The command line names one provider; an override moves an agent off it.

    Checking the flag alone would ask for a key the run never uses and miss the
    one it does.
    """
    resolved = resolve_agent_consumers(
        roles=[SENDER, RECEIVER],
        agent_overrides={"receiver": {"model": "gpt-5.4", "provider": "openai"}},
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
    )
    assert resolved == (
        ModelConsumer(name="sender", model="claude-sonnet-4-6", provider="anthropic"),
        ModelConsumer(name="receiver", model="gpt-5.4", provider="openai"),
    )


def test_every_agent_falls_back_to_the_command_line_model_and_provider() -> None:
    resolved = resolve_agent_consumers(
        roles=[SENDER, RECEIVER],
        agent_overrides=None,
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
    )
    assert {(entry.model, entry.provider) for entry in resolved} == {
        ("claude-sonnet-4-6", "anthropic")
    }


def test_the_message_says_what_to_do_and_who_needed_it() -> None:
    message = describe_unreachable_providers(
        unreachable=find_unreachable_providers(
            consumers=(
                ModelConsumer(name="sender", model="claude", provider="anthropic"),
                ModelConsumer(name="receiver", model="gemini", provider="google-gla"),
            )
        )
    )
    assert "ANTHROPIC_API_KEY" in message
    assert "GOOGLE_API_KEY or GEMINI_API_KEY" in message
    assert "sender" in message
    assert "receiver" in message
    assert ".env" in message


def test_the_run_is_refused_before_a_run_directory_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The refusal has to land before the directory is claimed.

    Everything after that point leaves a run behind that looks like it happened:
    a claimed directory, a JSONL, an `AgentRegistered` for every agent, and an
    exit status of 0. So the assertion is not only that it exits, but that
    nothing is on disk when it does.
    """
    runs_dir = tmp_path / "runs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "glossogen",
            "run",
            "prisoners_dilemma",
            "--model",
            "claude-sonnet-4-6",
            "--provider",
            "anthropic",
            "--runs-dir",
            str(runs_dir),
            "--config",
            "knobs_default",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert "ANTHROPIC_API_KEY" in str(raised.value)
    assert not runs_dir.exists()


def test_a_self_hosted_run_is_refused_before_a_run_directory_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The same guarantee for the model-not-served case.

    That one reaches the runner holding valid credentials, so it is the case a
    check on keys alone waves through.
    """
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", f'{{"{QWEN}":"https://example.modal.run/v1"}}')
    monkeypatch.setenv("SELF_HOSTED_API_KEY", "sh-secret")
    runs_dir = tmp_path / "runs"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "glossogen",
            "run",
            "prisoners_dilemma",
            "--model",
            LLAMA,
            "--provider",
            "self-hosted",
            "--runs-dir",
            str(runs_dir),
            "--config",
            "knobs_default",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        cli.main()

    assert "SELF_HOSTED_BASE_URLS has no endpoint" in str(raised.value)
    assert not runs_dir.exists()


def test_a_scenario_judge_is_checked_even_when_the_agents_authenticate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The judge runs under the provider the scenario's knobs name, not the run's.

    Every judge shipped here is `anthropic`, so an OpenAI run with only
    `OPENAI_API_KEY` reaches its agents and not its judge. The judge is built on
    first use, so without this the run starts, spends, and fails inside the tool
    call that scores the round.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    )
    with pytest.raises(ValueError) as raised:
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides=None,
            default_model="gpt-5.4",
            default_provider="openai",
        )
    assert "ANTHROPIC_API_KEY" in str(raised.value)
    assert "round judge" in str(raised.value)


def test_a_scenario_that_scores_without_an_llm_declares_no_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prisoner's dilemma resolves on arithmetic, so an OpenAI run needs one key."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    scenario_cls = get_scenario_class(name="prisoners_dilemma")
    config = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    )
    assert scenario_cls.get_judge_models(knobs=config) == ()
    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=config,
        agent_overrides=None,
        default_model="gpt-5.4",
        default_provider="openai",
    )
