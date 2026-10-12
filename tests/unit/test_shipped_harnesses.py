"""What the two CLI harnesses answer the launch check with, and what they build."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from glossogen.event_bus import EventBus
from glossogen.model_catalog import Provider
from glossogen.runners.claude_agent_sdk import cli_launcher
from glossogen.runners.claude_agent_sdk import harness as claude_harness
from glossogen.runners.claude_agent_sdk.harness import ClaudeAgentSdkHarness
from glossogen.runners.codex_app_server import harness as codex_harness
from glossogen.runners.codex_app_server.harness import CodexAppServerHarness
from glossogen.runners.harness_names import CLAUDE_AGENT_SDK_HARNESS_NAME, CODEX_HARNESS_NAME
from glossogen.runners.harness_protocol import HarnessSeat, RunnerBuildContext
from glossogen.runners.session_harness.runner import SessionSeatRunner

OPENAI_SEAT = HarnessSeat(name="engineer", model="gpt-5.4", provider=Provider.OPENAI)
ANTHROPIC_SEAT = HarnessSeat(
    name="observer", model="claude-sonnet-4-6", provider=Provider.ANTHROPIC
)


def hide_module(monkeypatch: pytest.MonkeyPatch, module_name: str) -> None:
    """Make ``find_spec`` answer as if ``module_name`` were not installed."""
    original: Callable[..., object] = importlib.util.find_spec

    def missing(name: str, package: str | None = None) -> object:
        if name == module_name:
            return None
        return original(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", missing)


def build_context(tmp_path: Path) -> RunnerBuildContext:
    return RunnerBuildContext(
        max_turns=1,
        event_bus=EventBus(max_queue_size=10),
        run_id="run",
        scenario_name="smoke",
        telemetry_enabled=False,
        run_dir=tmp_path,
    )


def test_the_cli_harnesses_name_themselves_and_cannot_gate_responses() -> None:
    assert ClaudeAgentSdkHarness.name() == CLAUDE_AGENT_SDK_HARNESS_NAME
    assert CodexAppServerHarness.name() == CODEX_HARNESS_NAME
    assert ClaudeAgentSdkHarness.gates_model_responses() is False
    assert CodexAppServerHarness.gates_model_responses() is False


def test_the_claude_harness_names_its_missing_extra_and_a_foreign_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hide_module(monkeypatch=monkeypatch, module_name=claude_harness.SDK_MODULE)

    remedies = ClaudeAgentSdkHarness.preflight(seats=(ANTHROPIC_SEAT, OPENAI_SEAT))

    assert remedies == (
        "install the harness-claude-agent-sdk extra: make install-server in a checkout, "
        "or depend on glossogen[harness-claude-agent-sdk]",
        "run these seats under provider anthropic; Claude Code drives Claude models only, "
        "not openai",
    )


def test_the_codex_harness_names_its_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    hide_module(monkeypatch=monkeypatch, module_name=codex_harness.BINARY_MODULE)

    remedies = CodexAppServerHarness.preflight(seats=(OPENAI_SEAT,))

    assert remedies == (
        "install the harness-codex extra: make install-server in a checkout, "
        "or depend on glossogen[harness-codex]",
    )


def test_the_claude_harness_builds_a_session_runner(tmp_path: Path) -> None:
    pytest.importorskip(claude_harness.SDK_MODULE)

    runner = ClaudeAgentSdkHarness.build_runner(context=build_context(tmp_path=tmp_path))

    assert isinstance(runner, SessionSeatRunner)


def test_the_codex_harness_builds_a_session_runner_on_the_bundled_binary(tmp_path: Path) -> None:
    binary_package: ModuleType = pytest.importorskip(codex_harness.BINARY_MODULE)

    runner = CodexAppServerHarness.build_runner(context=build_context(tmp_path=tmp_path))

    assert isinstance(runner, SessionSeatRunner)
    assert Path(binary_package.bundled_codex_path()).is_file()


def test_the_bundled_claude_cli_is_reported_missing_when_the_sdk_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hide_module(monkeypatch=monkeypatch, module_name=cli_launcher.SDK_PACKAGE)

    with pytest.raises(RuntimeError, match="is not installed"):
        cli_launcher.bundled_cli_path()
