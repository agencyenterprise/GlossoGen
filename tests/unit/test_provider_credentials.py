"""A run is refused at the command line when it cannot authenticate.

The cost of not checking is not a worse error message. Agent runner tasks are
awaited only after the game clock has finished, so a missing key surfaces after
the run's whole configured duration, from a run directory that was claimed and
written and holds a registration for every agent and a call to no model. The
tests below fix the two halves of avoiding that: which environments count as
unauthenticated, and that the refusal happens before anything is on disk.

The empty-string case is the one worth stating twice. `.env.example` ships every
key blank, so a copy that was never filled in sets the variable to nothing, and
a check reading only for presence would wave it through.
"""

import sys
from pathlib import Path

import pytest

from glossogen import cli
from glossogen.models.agent_config import AgentRole
from glossogen.provider_credentials import (
    AgentProvider,
    describe_missing_credentials,
    find_missing_credentials,
    resolve_agent_providers,
)

SENDER = AgentRole(agent_id="sender", role_name="Sender")
RECEIVER = AgentRole(agent_id="receiver", role_name="Receiver")

PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "HF_TOKEN",
    "SELF_HOSTED_BASE_URLS",
    "SELF_HOSTED_API_KEY",
)


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
    missing = find_missing_credentials(
        agent_providers=(AgentProvider(agent_id="sender", provider="anthropic"),)
    )
    assert missing == ()


def test_a_missing_key_names_the_variable_and_the_agents() -> None:
    missing = find_missing_credentials(
        agent_providers=(
            AgentProvider(agent_id="sender", provider="anthropic"),
            AgentProvider(agent_id="receiver", provider="anthropic"),
        )
    )
    assert len(missing) == 1
    assert missing[0].provider == "anthropic"
    assert missing[0].accepted_names == ("ANTHROPIC_API_KEY",)
    assert missing[0].agent_ids == ("receiver", "sender")


def test_a_key_set_to_blank_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env.example` ships every key empty, so this is the copied-and-unfilled case."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    missing = find_missing_credentials(
        agent_providers=(AgentProvider(agent_id="sender", provider="anthropic"),)
    )
    assert [entry.accepted_names for entry in missing] == [("ANTHROPIC_API_KEY",)]


def test_either_accepted_name_satisfies_a_provider_that_reads_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Google provider falls back to `GEMINI_API_KEY`, so that alone is enough."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-something")
    missing = find_missing_credentials(
        agent_providers=(AgentProvider(agent_id="sender", provider="google-gla"),)
    )
    assert missing == ()


def test_a_provider_with_nothing_to_authenticate_is_never_blocked() -> None:
    """A locally served provider needs no key, and one this table has never heard of
    must not be refused on the strength of that."""
    missing = find_missing_credentials(
        agent_providers=(
            AgentProvider(agent_id="sender", provider="ollama"),
            AgentProvider(agent_id="receiver", provider="something-new"),
        )
    )
    assert missing == ()


def test_a_provider_reading_two_values_reports_the_one_that_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", '{"m":"https://example/v1"}')
    missing = find_missing_credentials(
        agent_providers=(AgentProvider(agent_id="sender", provider="self-hosted"),)
    )
    assert [entry.accepted_names for entry in missing] == [("SELF_HOSTED_API_KEY",)]


def test_each_provider_the_run_uses_is_reported_separately() -> None:
    missing = find_missing_credentials(
        agent_providers=(
            AgentProvider(agent_id="sender", provider="anthropic"),
            AgentProvider(agent_id="receiver", provider="openai"),
        )
    )
    assert [(entry.provider, entry.agent_ids) for entry in missing] == [
        ("anthropic", ("sender",)),
        ("openai", ("receiver",)),
    ]


def test_an_override_decides_which_provider_an_agent_is_checked_against() -> None:
    """The command line names one provider; an override moves an agent off it.

    Checking the flag alone would ask for a key the run never uses and miss the
    one it does.
    """
    resolved = resolve_agent_providers(
        roles=[SENDER, RECEIVER],
        agent_overrides={"receiver": {"model": "gpt-5.4", "provider": "openai"}},
        default_provider="anthropic",
    )
    assert resolved == (
        AgentProvider(agent_id="sender", provider="anthropic"),
        AgentProvider(agent_id="receiver", provider="openai"),
    )


def test_every_agent_falls_back_to_the_command_line_provider() -> None:
    resolved = resolve_agent_providers(
        roles=[SENDER, RECEIVER],
        agent_overrides=None,
        default_provider="anthropic",
    )
    assert {entry.provider for entry in resolved} == {"anthropic"}


def test_the_message_says_what_to_set_and_who_needed_it() -> None:
    message = describe_missing_credentials(
        missing=find_missing_credentials(
            agent_providers=(
                AgentProvider(agent_id="sender", provider="anthropic"),
                AgentProvider(agent_id="receiver", provider="google-gla"),
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
    a claimed directory, a JSONL, an `AgentRegistered` for every agent. So the
    assertion is not only that it exits, but that nothing is on disk when it
    does.
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
