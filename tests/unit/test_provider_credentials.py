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

import argparse
import json
import sys
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from glossogen import cli
from glossogen.config_overrides import ResolvedAgentModel
from glossogen.model_catalog import Provider
from glossogen.models.agent_config import AgentRole
from glossogen.models.event import AgentRegistered
from glossogen.provider_credentials import (
    ModelConsumer,
    describe_unreachable_providers,
    find_unreachable_providers,
    require_reachable_models,
    resolve_agent_consumers,
    resolve_scheduled_swap_consumers,
)
from glossogen.resume_state_loader import refuse_resume_of_unrebuildable_seats
from glossogen.run_archive import resume_round_from_log
from glossogen.runners.harness_entry_points import HARNESS_ENTRY_POINT_GROUP
from glossogen.scenario_loader import get_scenario_class
from glossogen.testing.smoke_scenario import SmokeScenario
from tests.fakes.external_harness import EXTERNAL_HARNESS_NAME, MISSING_BINARY_REMEDY
from tests.fakes.installed_entry_points import declare_in_groups

SENDER = AgentRole(agent_id="sender", role_name="Sender")
RECEIVER = AgentRole(agent_id="receiver", role_name="Receiver")

LLAMA = "meta-llama/Llama-3.3-70B-Instruct"
QWEN = "Qwen/Qwen3-32B"

PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OLLAMA_BASE_URL",
    "HF_TOKEN",
    "SELF_HOSTED_BASE_URLS",
    "SELF_HOSTED_API_KEY",
)


def hosted(name: str, model: str) -> ModelConsumer:
    """Return one caller running a self-hosted model."""
    return ModelConsumer(name=name, model=model, provider=Provider.SELF_HOSTED)


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
        consumers=(ModelConsumer(name="sender", model="claude", provider=Provider.ANTHROPIC),)
    )
    assert unreachable == ()


def test_a_missing_key_names_the_variable_and_the_agents() -> None:
    unreachable = find_unreachable_providers(
        consumers=(
            ModelConsumer(name="sender", model="claude", provider=Provider.ANTHROPIC),
            ModelConsumer(name="receiver", model="claude", provider=Provider.ANTHROPIC),
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
        consumers=(ModelConsumer(name="sender", model="claude", provider=Provider.ANTHROPIC),)
    )
    assert [entry.remedy for entry in unreachable] == ["set ANTHROPIC_API_KEY"]


def test_either_accepted_name_satisfies_a_provider_that_reads_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Google provider falls back to `GEMINI_API_KEY`, so that alone is enough."""
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-something")
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="gemini", provider=Provider.GOOGLE_GLA),)
    )
    assert unreachable == ()


def test_ollama_requires_the_endpoint_pydantic_ai_uses() -> None:
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="llama3", provider=Provider.OLLAMA),)
    )
    assert len(unreachable) == 1
    assert unreachable[0].remedy == "set OLLAMA_BASE_URL"


def test_ollama_with_an_endpoint_is_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    unreachable = find_unreachable_providers(
        consumers=(ModelConsumer(name="sender", model="llama3", provider=Provider.OLLAMA),)
    )
    assert unreachable == ()


def test_compaction_under_a_provider_the_runner_cannot_compact_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner has a compaction capability for Anthropic and OpenAI only.

    Under any other provider the knob changed nothing and said nothing, so a
    run that asked for compaction ran uncompacted at full context cost.
    """
    scenario_cls = get_scenario_class(name="hospital_bed_assignment_privacy")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    config["compaction"] = {"enabled": True, "token_threshold": 60_000}
    with pytest.raises(ValueError, match="compaction.enabled is set") as excinfo:
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides=None,
            default_model="llama",
            default_provider="ollama",
            default_harness="pydantic-ai",
            first_round=1,
        )
    assert "ollama" in str(excinfo.value)


def test_compaction_under_a_compacting_provider_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    scenario_cls = get_scenario_class(name="hospital_bed_assignment_privacy")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    config["compaction"] = {"enabled": True, "token_threshold": 60_000}
    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=config,
        agent_overrides=None,
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
        default_harness="pydantic-ai",
        first_round=1,
    )


def test_anthropic_compaction_below_the_provider_minimum_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")
    scenario_cls = get_scenario_class(name="hospital_bed_assignment_privacy")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    config["compaction"] = {"enabled": True, "token_threshold": 49_999}

    with pytest.raises(ValueError, match="at least 50000 for Anthropic"):
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides=None,
            default_model="claude-sonnet-4-6",
            default_provider="anthropic",
            default_harness="pydantic-ai",
            first_round=1,
        )


def test_each_provider_the_run_uses_is_reported_separately() -> None:
    unreachable = find_unreachable_providers(
        consumers=(
            ModelConsumer(name="sender", model="claude", provider=Provider.ANTHROPIC),
            ModelConsumer(name="receiver", model="gpt", provider=Provider.OPENAI),
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
    """`model_catalog` swallows this and reports no self-hosted models, so a run
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
        agent_overrides={
            "receiver": ResolvedAgentModel(
                model="gpt-5.4", provider=Provider.OPENAI, harness="pydantic-ai"
            )
        },
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
    )
    assert resolved == (
        ModelConsumer(name="sender", model="claude-sonnet-4-6", provider=Provider.ANTHROPIC),
        ModelConsumer(name="receiver", model="gpt-5.4", provider=Provider.OPENAI),
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
                ModelConsumer(name="sender", model="claude", provider=Provider.ANTHROPIC),
                ModelConsumer(name="receiver", model="gemini", provider=Provider.GOOGLE_GLA),
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
            default_harness="pydantic-ai",
            first_round=1,
        )
    assert "ANTHROPIC_API_KEY" in str(raised.value)
    assert "round judge" in str(raised.value)


def test_a_judge_under_a_provider_no_judge_runs_under_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`judge_provider` accepts any provider, but a judge is built by `create_provider`.

    With that provider's key set, the credential check alone passes, and the judge
    would fail at its first call after the run started.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("XAI_API_KEY", "xai-key")
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.prepare_config(
        config=dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    )
    config["judge_model"] = "grok-4.6"
    config["judge_provider"] = "xai"
    with pytest.raises(ValueError) as raised:
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides=None,
            default_model="gpt-5.4",
            default_provider="openai",
            first_round=1,
        )
    assert "round judge (xai)" in str(raised.value)
    assert "anthropic, huggingface, openai" in str(raised.value)


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
        default_harness="pydantic-ai",
        first_round=1,
    )


def veyru_config_with_a_swap(model: str, provider: str) -> dict[str, object]:
    """Veyru's default preset, plus a swap that brings in another provider."""
    scenario_cls = get_scenario_class(name="veyru")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config["scheduled_events"] = [
        {
            "type": "swap_agent",
            "at_round": 5,
            "agent_id": "field_observer",
            "model": model,
            "provider": provider,
            "channel_visibility": {},
        }
    ]
    return config


def test_a_scheduled_swap_is_a_caller_like_any_other() -> None:
    """The entry names its own model, and the runtime builds it at a boundary."""
    resolved = resolve_scheduled_swap_consumers(
        scenario_cls=get_scenario_class(name="veyru"),
        scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
        first_round=1,
    )
    assert [(entry.model, entry.provider) for entry in resolved] == [("gpt-5.4", "openai")]
    assert "round 5" in resolved[0].name


def test_a_swap_to_a_provider_with_no_credential_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The most expensive shape of this failure, and the last one to surface.

    The agents authenticate, so the run starts and pays for every round up to
    the swap before the provider it cannot reach is touched.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    with pytest.raises(ValueError) as refused:
        require_reachable_models(
            scenario_cls=get_scenario_class(name="veyru"),
            scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
            agent_overrides=None,
            default_model="claude-sonnet-4-6",
            default_provider="anthropic",
            default_harness="pydantic-ai",
            first_round=1,
        )
    message = str(refused.value)
    assert "OPENAI_API_KEY" in message
    assert "field_observer swapped in at round 5" in message


def test_a_swap_the_environment_can_reach_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key for the provider the swap brings in is all it takes."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-something")
    require_reachable_models(
        scenario_cls=get_scenario_class(name="veyru"),
        scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
        agent_overrides=None,
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
        default_harness="pydantic-ai",
        first_round=1,
    )


def test_a_scenario_that_names_no_judge_asks_for_nothing_on_its_behalf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scoring by comparison needs no model, so no key stands between it and a run.

    `hospital_bed_assignment_privacy` carried judge knobs it never read, which
    is how a scenario with no LLM anywhere came to demand an Anthropic key.
    """
    scenario_cls = get_scenario_class(name="hospital_bed_assignment_privacy")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    assert scenario_cls.get_judge_models(knobs=config) == ()
    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=config,
        agent_overrides=None,
        default_model="llama",
        default_provider="ollama",
        default_harness="pydantic-ai",
        first_round=1,
    )


def test_a_swap_the_resumed_run_has_already_outlived_is_not_asked_for() -> None:
    """A resume inherits the source's whole schedule, including spent boundaries.

    The multi-swap shape this exists for: phase B moved an agent to another
    provider at round 16, phase C moved it back, and a resume at 40 crosses
    neither. Asking for the key refuses a run for a model nothing will call,
    and the likeliest one to be gone is a self-hosted endpoint that has since
    been stopped.
    """
    assert (
        resolve_scheduled_swap_consumers(
            scenario_cls=get_scenario_class(name="veyru"),
            scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
            first_round=40,
        )
        == ()
    )


def test_a_swap_at_the_round_a_resume_opens_on_is_asked_for() -> None:
    """It fires: the cloned log stops before the source dispatched that boundary."""
    resolved = resolve_scheduled_swap_consumers(
        scenario_cls=get_scenario_class(name="veyru"),
        scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
        first_round=5,
    )
    assert [(entry.model, entry.provider) for entry in resolved] == [("gpt-5.4", "openai")]


def test_resuming_past_a_swap_needs_no_key_for_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal this boundary exists to prevent, through the launch check."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    require_reachable_models(
        scenario_cls=get_scenario_class(name="veyru"),
        scenario_config=veyru_config_with_a_swap(model="gpt-5.4", provider=Provider.OPENAI),
        agent_overrides=None,
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
        default_harness="pydantic-ai",
        first_round=40,
    )


def test_the_round_a_resume_opens_on_is_read_from_the_log(tmp_path: Path) -> None:
    """Preflight has only the run directory, and needs the boundary before loading it."""
    log = tmp_path / "veyru.jsonl"
    log.write_text(
        '{"event_type": "round_advanced", "round_number": 1}\n'
        '{"event_type": "message_sent", "round_number": 1}\n'
        '{"event_type": "round_advanced", "round_number": 16}\n'
    )
    assert resume_round_from_log(log_path=log) == 16


def test_a_run_with_no_log_yet_opens_at_one(tmp_path: Path) -> None:
    """A missing directory is somebody else's error to report, not this one's."""
    assert resume_round_from_log(log_path=tmp_path / "absent.jsonl") == 1


def declare_external_harnesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install the fake harnesses: one ready, one whose launch check names a remedy."""
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                EntryPoint(
                    name=EXTERNAL_HARNESS_NAME,
                    value="tests.fakes.external_harness:ExternalHarness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                ),
            ]
        },
    )


def test_a_harness_that_cannot_hold_responses_is_refused_where_the_scenario_needs_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Textcraft's virtual clock holds each response until its simulated turn.

    A harness that learns of a response only once its tools already run would
    let agents act out of turn, and the run would report a clock it never kept.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    declare_external_harnesses(monkeypatch=monkeypatch)
    scenario_cls = get_scenario_class(name="textcraft_shared_workspace")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    assert scenario_cls.requires_gated_model_responses(knobs=config)
    with pytest.raises(ValueError, match="holds each model response"):
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides=None,
            default_model="claude-sonnet-4-6",
            default_provider="anthropic",
            default_harness=EXTERNAL_HARNESS_NAME,
            first_round=1,
        )


def test_the_same_scenario_without_the_virtual_clock_accepts_that_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    declare_external_harnesses(monkeypatch=monkeypatch)
    scenario_cls = get_scenario_class(name="textcraft_shared_workspace")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config["virtual_clock"] = False
    config["craft_duration_s"] = 0
    require_reachable_models(
        scenario_cls=scenario_cls,
        scenario_config=config,
        agent_overrides=None,
        default_model="claude-sonnet-4-6",
        default_provider="anthropic",
        default_harness=EXTERNAL_HARNESS_NAME,
        first_round=1,
    )


def test_a_harness_reports_what_it_is_missing_with_the_seats_it_would_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the harness knows what it needs beyond the provider's key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    declare_in_groups(
        monkeypatch=monkeypatch,
        groups={
            HARNESS_ENTRY_POINT_GROUP: [
                EntryPoint(
                    name=EXTERNAL_HARNESS_NAME,
                    value="tests.fakes.external_harness:UnreadyExternalHarness",
                    group=HARNESS_ENTRY_POINT_GROUP,
                ),
            ]
        },
    )
    scenario_cls = get_scenario_class(name="veyru")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    with pytest.raises(ValueError, match=MISSING_BINARY_REMEDY) as excinfo:
        require_reachable_models(
            scenario_cls=scenario_cls,
            scenario_config=config,
            agent_overrides={
                "field_observer": ResolvedAgentModel(
                    model="claude-sonnet-4-6",
                    provider=Provider.ANTHROPIC,
                    harness=EXTERNAL_HARNESS_NAME,
                )
            },
            default_model="claude-sonnet-4-6",
            default_provider="anthropic",
            default_harness="pydantic-ai",
            first_round=1,
        )
    assert "field_observer" in str(excinfo.value)
    assert "stabilization_engineer" not in str(excinfo.value)


def test_a_scheduled_swap_onto_a_harness_that_cannot_take_a_history_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A swap seeds the new seat with a reconstructed pydantic-ai history."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-something")
    config = veyru_config_with_a_swap(model="claude-sonnet-4-6", provider=Provider.ANTHROPIC)
    swaps = config["scheduled_events"]
    assert isinstance(swaps, list)
    swaps[0]["harness"] = "claude-agent-sdk"
    with pytest.raises(ValueError, match="reconstructed history"):
        require_reachable_models(
            scenario_cls=get_scenario_class(name="veyru"),
            scenario_config=config,
            agent_overrides=None,
            default_model="claude-sonnet-4-6",
            default_provider="anthropic",
            default_harness="pydantic-ai",
            first_round=1,
        )


def test_a_scenario_that_overrides_the_gate_needs_it_held_unless_it_says_otherwise() -> None:
    """A scenario written before the hook existed is not assumed to do nothing in its gate."""

    class GatingScenario(SmokeScenario):
        async def gate_model_response(
            self, agent_id: str, input_tokens: int, output_tokens: int
        ) -> None:
            _ = agent_id, input_tokens, output_tokens

    assert not SmokeScenario.requires_gated_model_responses(knobs=None)
    assert GatingScenario.requires_gated_model_responses(knobs=None)


def test_an_agents_override_on_the_command_line_keeps_the_fields_the_config_file_set(
    tmp_path: Path,
) -> None:
    """``agents.<id>.harness=`` alone moves the seat to a harness on the model the file chose."""
    scenario_cls = get_scenario_class(name="veyru")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config["model_overrides"] = {"field_observer": {"model": "gpt-5.4", "provider": "openai"}}
    config_path = tmp_path / "knobs.json"
    config_path.write_text(json.dumps(config))

    built = cli.build_run_config(
        args=argparse.Namespace(config=str(config_path)),
        remaining=["agents.field_observer.harness=codex"],
        scenario_cls=scenario_cls,
    )

    assert built["model_overrides"] == {
        "field_observer": {"model": "gpt-5.4", "provider": "openai", "harness": "codex"}
    }


def test_a_model_override_on_the_command_line_drops_the_providers_the_config_file_set(
    tmp_path: Path,
) -> None:
    """A model named alone falls back to ``--provider``, never to the file's vendor."""
    scenario_cls = get_scenario_class(name="veyru")
    config = dict(scenario_cls.load_knobs_preset(preset_name="knobs_default"))
    config["model_overrides"] = {
        "field_observer": {"model": "gpt-5.4", "provider": "openai", "harness": "codex"}
    }
    config_path = tmp_path / "knobs.json"
    config_path.write_text(json.dumps(config))

    built = cli.build_run_config(
        args=argparse.Namespace(config=str(config_path)),
        remaining=["agents.field_observer.model=claude-opus-4-6"],
        scenario_cls=scenario_cls,
    )

    assert built["model_overrides"] == {
        "field_observer": {"model": "claude-opus-4-6", "harness": "codex"}
    }


def write_seat_log(run_dir: Path, lines: list[dict[str, object]]) -> None:
    (run_dir / "veyru.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))


def registered(agent_id: str, harness: str) -> dict[str, object]:
    return AgentRegistered(
        agent_id=agent_id,
        round_number=1,
        role_name=agent_id,
        system_prompt="",
        channel_ids=[],
        tool_names=[],
        model="gpt-5.4",
        provider="openai",
        harness=harness,
        max_tokens=2048,
    ).model_dump(mode="json")


def test_resuming_a_run_whose_cli_seat_was_swapped_onto_pydantic_ai_is_allowed(
    tmp_path: Path,
) -> None:
    write_seat_log(
        run_dir=tmp_path,
        lines=[
            registered(agent_id="field_observer", harness="codex"),
            {
                "event_type": "agent_swapped_mid_run",
                "round_number": 3,
                "agent_id": "field_observer",
                "new_model": "gpt-5.4",
                "new_provider": "openai",
                "new_harness": "pydantic-ai",
                "channel_visibility": {},
            },
        ],
    )

    refuse_resume_of_unrebuildable_seats(resume_dir=tmp_path, scenario_name="veyru")


def test_resuming_a_run_keeping_a_cli_seat_is_refused_before_the_run_starts(
    tmp_path: Path,
) -> None:
    write_seat_log(run_dir=tmp_path, lines=[registered(agent_id="field_observer", harness="codex")])

    with pytest.raises(ValueError, match=r"field_observer \(codex\)"):
        refuse_resume_of_unrebuildable_seats(resume_dir=tmp_path, scenario_name="veyru")
