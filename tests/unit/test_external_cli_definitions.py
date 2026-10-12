"""How each CLI is started for a seat, and what its output is read as."""

import json
import shutil
from pathlib import Path

import pytest

from glossogen.event_bus import EventBus
from glossogen.model_catalog import Provider
from glossogen.models.event_base import TokenUsage
from glossogen.runners.external_cli import claude_code, codex
from glossogen.runners.external_cli.claude_code import ClaudeCodeCli, ClaudeCodeHarness
from glossogen.runners.external_cli.cli_protocol import CliSeat, CliTurn
from glossogen.runners.external_cli.cli_seat_runner import ExternalCliRunner, failure_pause_seconds
from glossogen.runners.external_cli.codex import CodexCli, CodexHarness
from glossogen.runners.harness_protocol import HarnessSeat, RunnerBuildContext


def seat(tmp_path: Path) -> CliSeat:
    return CliSeat(
        agent_id="field_observer",
        model="some-model",
        system_prompt="You observe.",
        max_output_tokens=2048,
        state_dir=tmp_path / "harness_state",
        workspace=tmp_path / "harness_state" / "workspace",
        tool_url="http://127.0.0.1:5555/mcp",
        tool_token="secret-token",
    )


def test_claude_code_is_started_with_only_the_seats_server_and_resumes_its_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "a credential the seat must not use")
    monkeypatch.setenv("ANTHROPIC_IDENTITY_TOKEN", "another")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    cli = ClaudeCodeCli(binary="/usr/local/bin/claude")
    cli.prepare(seat=seat(tmp_path=tmp_path))

    first = cli.command(
        seat=seat(tmp_path=tmp_path), turn=CliTurn(prompt="Begin.", resume_session_id=None)
    )
    later = cli.command(
        seat=seat(tmp_path=tmp_path), turn=CliTurn(prompt="Go on.", resume_session_id="s-1")
    )
    environment = cli.environment(seat=seat(tmp_path=tmp_path))

    assert first[:4] == ["/usr/local/bin/claude", "--print", "--output-format", "json"]
    mcp_config = json.loads(first[first.index("--mcp-config") + 1])
    assert mcp_config["mcpServers"]["glossogen"] == {
        "type": "http",
        "url": "http://127.0.0.1:5555/mcp",
        "headers": {"Authorization": "Bearer secret-token"},
    }
    assert "--strict-mcp-config" in first
    assert first[first.index("--tools") + 1] == ""
    assert first[first.index("--allowed-tools") + 1] == "mcp__glossogen__*"
    assert first[first.index("--system-prompt") + 1] == "You observe."
    assert "--session-id" in first and first[-1] == "Begin."
    assert later[later.index("--resume") + 1] == "s-1" and "--session-id" not in later
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in environment
    assert "ANTHROPIC_IDENTITY_TOKEN" not in environment
    assert environment["ANTHROPIC_API_KEY"] == "sk-ant"
    assert environment["CLAUDE_CONFIG_DIR"] == str(tmp_path / "harness_state" / "claude_config")
    assert environment["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "2048"
    assert (tmp_path / "harness_state" / "claude_config").is_dir()


def test_claude_codes_result_is_read_with_the_whole_input_counted() -> None:
    cli = ClaudeCodeCli(binary="claude")
    result = cli.parse_output(
        stdout=json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": "s-1",
                "total_cost_usd": 0.0123,
                "usage": {
                    "input_tokens": 3,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 200,
                    "output_tokens": 40,
                },
            }
        )
    )

    assert result.session_id == "s-1"
    assert result.reported_cost_usd == 0.0123
    assert result.usage == TokenUsage(
        input_tokens=1203,
        output_tokens=40,
        cache_read_input_tokens=1000,
        cache_creation_input_tokens=200,
    )
    assert not result.is_error


def test_claude_codes_failure_carries_its_explanation_and_unreadable_output_is_refused() -> None:
    cli = ClaudeCodeCli(binary="claude")
    failed = cli.parse_output(
        stdout=json.dumps(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "session_id": "s-1",
                "errors": ["API Error: overloaded"],
            }
        )
    )

    assert failed.is_error and failed.error_text == "API Error: overloaded"
    with pytest.raises(ValueError, match="no result"):
        cli.parse_output(stdout="")
    with pytest.raises(ValueError, match="not the expected JSON"):
        cli.parse_output(stdout="not json")


def test_codex_is_started_on_the_seats_instructions_and_server_and_resumes_its_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_API_KEY", "a credential the seat must not use")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    cli = CodexCli(binary="/usr/local/bin/codex")
    cli.prepare(seat=seat(tmp_path=tmp_path))

    first = cli.command(
        seat=seat(tmp_path=tmp_path), turn=CliTurn(prompt="Begin.", resume_session_id=None)
    )
    later = cli.command(
        seat=seat(tmp_path=tmp_path), turn=CliTurn(prompt="Go on.", resume_session_id="t-1")
    )
    environment = cli.environment(seat=seat(tmp_path=tmp_path))

    assert first[:2] == ["/usr/local/bin/codex", "exec"]
    assert later[:3] == ["/usr/local/bin/codex", "exec", "resume"]
    assert later[-2:] == ["t-1", "Go on."]
    overrides = [first[index + 1] for index, flag in enumerate(first) if flag == "-c"]
    assert 'mcp_servers.glossogen.url="http://127.0.0.1:5555/mcp"' in overrides
    assert 'mcp_servers.glossogen.bearer_token_env_var="GLOSSOGEN_AGENT_TOKEN"' in overrides
    assert f"mcp_servers.glossogen.tool_timeout_sec={codex.TOOL_TIMEOUT_SECONDS}" in overrides
    assert 'base_url="https://proxy.example/v1"' in " ".join(overrides)
    instructions = tmp_path / "harness_state" / "model_instructions.md"
    assert f'model_instructions_file="{instructions}"' in overrides
    assert instructions.read_text() == "You observe."
    assert "CODEX_API_KEY" not in environment
    assert environment["CODEX_HOME"] == str(tmp_path / "harness_state" / "codex_home")
    assert environment["GLOSSOGEN_AGENT_TOKEN"] == "secret-token"


def test_codexs_json_lines_give_the_thread_the_usage_and_the_failure() -> None:
    cli = CodexCli(binary="codex")
    lines = [
        {"type": "thread.started", "thread_id": "t-1"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 500, "cached_input_tokens": 100, "output_tokens": 20},
        },
    ]

    result = cli.parse_output(stdout="\n".join(json.dumps(line) for line in lines))

    assert result.session_id == "t-1"
    assert result.usage == TokenUsage(
        input_tokens=500,
        output_tokens=20,
        cache_read_input_tokens=100,
        cache_creation_input_tokens=0,
    )
    assert not result.is_error
    failed = cli.parse_output(
        stdout=json.dumps({"type": "turn.failed", "error": {"message": "rate limited"}})
    )
    assert failed.is_error and failed.error_text == "rate limited"
    with pytest.raises(ValueError, match="neither turn.completed nor a failure"):
        cli.parse_output(stdout="not json\n")


def test_the_harnesses_name_the_missing_binary_and_a_foreign_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def nothing_on_path(name: str) -> None:
        _ = name
        return None

    monkeypatch.setattr(shutil, "which", nothing_on_path)
    seats = (
        HarnessSeat(name="observer", model="claude-sonnet-4-6", provider=Provider.ANTHROPIC),
        HarnessSeat(name="engineer", model="gpt-5.4", provider=Provider.OPENAI),
    )

    assert ClaudeCodeHarness.preflight(seats=seats) == (
        "put the Claude Code CLI (claude) on PATH; npm install -g @anthropic-ai/claude-code "
        "installs it",
        "run these seats under provider anthropic; Claude Code drives Claude models only, "
        "not openai",
    )
    assert CodexHarness.preflight(seats=seats) == (
        "put the Codex CLI (codex) on PATH; npm install -g @openai/codex installs it",
        "run these seats under provider openai; Codex drives OpenAI models only, not anthropic",
    )
    assert ClaudeCodeHarness.gates_model_responses() is False
    assert CodexHarness.gates_model_responses() is False


def test_the_harnesses_build_a_runner_over_the_binary_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def on_path(name: str) -> str:
        return f"/usr/local/bin/{name}"

    monkeypatch.setattr(shutil, "which", on_path)
    context = RunnerBuildContext(
        max_turns=1,
        event_bus=EventBus(max_queue_size=10),
        run_id="run",
        scenario_name="smoke",
        telemetry_enabled=False,
        run_dir=tmp_path,
    )

    assert isinstance(ClaudeCodeHarness.build_runner(context=context), ExternalCliRunner)
    assert isinstance(CodexHarness.build_runner(context=context), ExternalCliRunner)
    assert claude_code.BINARY_NAME == "claude" and codex.BINARY_NAME == "codex"


def test_the_pause_after_failures_doubles() -> None:
    assert [failure_pause_seconds(consecutive_failures=n) for n in (1, 2)] == [30.0, 60.0]
